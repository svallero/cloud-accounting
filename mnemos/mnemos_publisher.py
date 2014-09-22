#!/usr/bin/python

###############################################################################
#                                                                             #
# Daemon to backup accounting data in dedicated DB                            #
# and take action if quotas are exceeded.                                     #
#                                                                             #
# The DB is structured in a way to be easily read by Logstash.                #
#                                                                             #
# This is the publisher daemon, that sends inserts request and alarms         #
# to RabbitMQ queues.                                                         #
#                                                                             #
# In the main loop we do:                                                     #
#                                                                             #
# TODO                                                                        #
#                                                                             #
# Based on python module "daemon", which implements the well-behaved          #
# daemon specification of PEP3143.                                            # 
#                                                                             #
# To kick off the script, run the following from the python directory:        #
#                                                                             #
# python mnemos_publisher.py start                                            # 
#                                                                             #
# Init script: bin/mnemos                                                     #
#                                                                             #
# Mailto: svallero@to.infn.it                                                 #
#                                                                             #
###############################################################################

# Standard python libs
import ast
import gzip
import base64
import mimetypes
import socket
import struct
import logging
import boto
import time
import sys
import os
import pika
import time
import pwd
import subprocess
from subprocess import Popen, PIPE
from ConfigParser import SafeConfigParser



# Third party libs
from daemon import runner

# Global vars
global logfile
logfile = '/dev/null'

# Daemon class, main loop is defined here -------------------------------------
class App():
    
    def __init__(self):
        self.stdin_path = '/dev/null'
        self.stdout_path = '/dev/tty'
        self.stderr_path = '/dev/tty'
        self.pidfile_timeout = 5
        self.pidfile_path = '/var/run/mnemos/mnemos_publisher.pid' 
    
    def run(self):
        logger.info("**************************************")
        logger.info("*** Starting daemon mnemos.py      ***")
        logger.info("**************************************")
        print_config()       
        logger.info("--------------------------------------")
         
        # LOAD CLOUD PLUGIN
        logger.info('Loading cloud plugin...')
        try:
           cloud_plugin = getattr(__import__('mnemos.plugins', fromlist=[ cloud_name ]), cloud_name)
        except (ImportError, AttributeError) as e:
           logger.fatal('Cannot find cloud plugin: '+cloud_name+'')
           sys.exit(2)

        logger.info('Loaded cloud plugin: '+cloud_name+'')

        # Init cloud plugin
        logger.info('Init cloud plugin...')
        cloud_plugin.init(cloud_cf,logger)
        logger.info("--------------------------------------")

        # LOAD DB PLUGIN
        logger.info('Loading database plugin...')
        global db_plugin
        try:
           db_plugin = getattr(__import__('mnemos.plugins', fromlist=[ db_name ]), db_name)
        except (ImportError, AttributeError) as e:
           logger.fatal('Cannot find database plugin: '+db_name+'')
           sys.exit(2)

        logger.info('Loaded database plugin: '+db_name+'')

        # Init db plugin
        logger.info('Init database plugin...')
        db_plugin.init(db_cf,logger)
        logger.info("**************************************")

 
        # MAIN LOOP
        # count the loops
        count=0
        while True:
            timestamp=int(time.time())
            count +=1
            logger.info('Loop '+str(count)+'...')
            # Initialize connection to RabbitMQ
            connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
            channel=connection.channel() 
            # create the queues TODO: do not hardcode queue name!
            queue=channel.queue_declare(queue='mnemos',durable=True)
            queue=channel.queue_declare(queue='summary',durable=True)
            queue=channel.queue_declare(queue='summary_db',durable=True)
            queue=channel.queue_declare(queue='alarms',durable=True)

            # Get accounting info
            logger.info('Getting accounting information from cloud...')
            val=cloud_plugin.get_accounting_data(timestamp)
            # Send to rabbit queue (at each loop)
            logger.info('Publishing data in queue \'mnemos\'...')
            for message in val.items():
               channel.basic_publish(exchange='',routing_key='mnemos',body=str(message[1]), properties=pika.BasicProperties(delivery_mode = 2))
               logger.debug('Sent: '+str(message[1])+'')

            
            # Get quotas per user
            #logger.info('Query the database for quotas...')
            # below to take quotas from database table
            #quotas=db_plugin.get_quotas()
            # else quotas are taken from file
            logger.info('Read quotas from file...')
            quotas=[]
            f=open(quotas_file,'r')
            for line in f:
               if '#' not in line:
                  quotas.append(line.strip().split())
            f.close()
            # summary is published only each 'cycles_to_summary' loops
            pub_sum = False
            if count == int(cycles_to_summary):
               pub_sum=True
               count=0
            for q in quotas:
               # Get summary per user
               user=str(q[0])
               starttime=int(q[1])
               maxcputime=int(q[2])
               logger.info('Creating summary for user '+user+'...')
               summary=db_plugin.get_summary(user,int(starttime))
               # convert resource times in days from seconds
               usedcputime=summary['cpu-time']/86400
               usedmemtime=summary['memory-time']/86400
               useddisktime=summary['disk-time']/86400
               usedvms=summary['#vms']
               # qui occhio a GMT...
               startday=time.strftime("%d/%m/%y %H:%M",time.localtime(summary['start']))
               if not summary['stop']:
                  stopday=time.strftime("%d/%m/%y %H:%M",time.localtime(timestamp))
                  # unformatted timestamp for database
                  ustopday=timestamp
               else:
                  stopday=time.strftime("%d/%m/%y %H:%M",time.localtime(summary['stop']))
                  # unformatted timestamp for database
                  ustopday=summary['stop']
               if pub_sum:
                  logger.info('Publishing summary in queue \'summary\'...')
                  summary_text='SUMMARY - user='+user+' #vms='+str(usedvms)+' cpu-time='+str(usedcputime)+' (cpus*days) memory-time='+str(usedmemtime)+' (MB*days) disk-time='+str(useddisktime)+' (MB*days) in period '+str(startday)+' - '+str(stopday)+'' 
                  channel.basic_publish(exchange='',routing_key='summary',body=str(summary_text),properties=pika.BasicProperties(delivery_mode = 2))
                  logger.debug('Sent: '+str(summary)+'')
                  

                  logger.info('Publishing summary in queue \'summary_db\'...')
                  summary_db={'user': user, 'starttime': starttime, 'maxcputime': maxcputime, 'stoptime': ustopday, 'cputime': summary['cpu-time'], 'memorytime': summary['memory-time'], 'disktime': summary['disk-time'], 'nvms': summary['#vms']}
                  channel.basic_publish(exchange='',routing_key='summary_db',body=str(summary_db), properties=pika.BasicProperties(delivery_mode = 2))
                  logger.debug('Sent: '+str(summary_db)+'')

               # Check if quota was exceeded
               logger.info('Checking if '+user+' has exceeded quota...')
               alarm=''
               if usedcputime > maxcputime:
                  alarm='CPU QUOTA ALARM - User *** '+user+' *** has used '+str(usedcputime)+'/'+str(maxcputime)+' cpus*day from '+str(startday)+' to '+str(stopday)+''
                  #logger.info(alarm)
                  logger.info('Publishing alarm in queue \'alarms\'...')
                  channel.basic_publish(exchange='',routing_key='alarms',body=alarm,properties=pika.BasicProperties(delivery_mode = 2))
                  logger.debug('Sent: '+alarm+'')
               #else:
               #   logger.info('OK - user: '+user+' has used '+str(usedcputime)+'/'+str(maxcputime)+' cpus*day from '+str(startday)+' to '+str(stopday)+'') 

            connection.close()
           
            # Sleep   
            logger.info('Sleeping '+str(sleep_time)+'s...')
            time.sleep(int(sleep_time))

# Configuration ---------------------------------------------------------------
def configure(config_file):
   if not config_file:
      print "==> ERROR: configuration file not specified!!!"
      sys.exit(1)
   else:
       print "==> Reading configuration file..."
       cf_parser = SafeConfigParser()
       if len(cf_parser.read(config_file)) == 0:
          print ('Cannot read configuration file: %s!' % config_file)
          sys.exit(1)
       for key,val in cf_parser.items('mnemos'): 
         globals() [key]=val
       # logfile
       global logfile
       logfile=''+logdir+'/mnemos_publisher.log'
       # touch logfile 
       if not os.path.exists(os.path.dirname(logfile)):
          os.system('sudo mkdir -p '+os.path.dirname(logfile)+'')
       os.system('sudo touch '+logfile+'')
       os.system('sudo chown mnemos:mnemos '+logfile+'')
       # config cloud plugin
       global cloud_cf
       cloud_cf = cf_parser.items(cloud_name)
       # config database plugin
       global db_cf
       db_cf = cf_parser.items(db_name)
        

def print_config():
   # print configuration to logger 
   logger.info('CONFIGURATION:')
   logger.info('[mnemos]') 
   logger.info('   sleep_time='+str(sleep_time)+'') 
   logger.info('   cycles_to_summary='+str(cycles_to_summary)+'') 
   logger.info('   quotas_file='+str(quotas_file)+'') 
   logger.info('   logfile='+logfile+'')
   logger.info('   cloud_name='+cloud_name+'')
   logger.info('   db_name='+db_name+'')

# Logger ---------------------------------------------------------------------- 
def define_logger(level,logfile):
   global logger
   logger = logging.getLogger("mnemos")
   if level == 'DEBUG':
      logger.setLevel(logging.DEBUG)
   if level == 'INFO':
      logger.setLevel(logging.INFO)
   if level == 'ERROR':
      logger.setLevel(logging.ERROR)
   formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
   global lhandler
   lhandler = logging.FileHandler(logfile)
   lhandler.setFormatter(formatter)
   logger.addHandler(lhandler)

# Custom daemon runner --------------------------------------------------------
class MyDaemonRunner(runner.DaemonRunner):
    def __init__(self, app):
        # workaround...
        self.app_save = app
 
        self.detach_process = True
        runner.DaemonRunner.__init__(self, app)
 
    def parse_args(self, argv=None):
        # Note that DaemonRunner implements its own parse_args(), and
        # it is called in __init__ of the class.
        # Here, we override it using argparse.
        import argparse
        log_level=''
	parser = argparse.ArgumentParser('mnemos')
        parser.add_argument('-c', '--configfile', help='path to configuration file')
        parser.add_argument('-l', '--loglevel', help='DEBUG|INFO|ERROR (default=INFO)')
        parser.add_argument('action', help='start|stop|restart')
        args = parser.parse_args()
        # action
        self.action =  args.action 
        if self.action not in self.action_funcs:
            self._usage_exit(sys.argv)
        # log level
        log_level=args.loglevel
        if not log_level:
           log_level='INFO'
        if log_level not in ['DEBUG','INFO','ERROR']:  
           print 'allowed log levels: DEBUG, INFO, ERROR'
           sys.exit(2) 
        # config file
        config_file=args.configfile
        if self.action != 'stop':
           # apply configuration
           configure(config_file)
        # define logger
        define_logger(log_level, logfile) 

# ENTRY POINT #

# Switch user
uid = pwd.getpwnam('mnemos')[2]
if not uid:
   print '== FATAL: user \'mnemos\' does not exist! =='
   sys.exit(1)
os.setuid(uid)

# Define daemon runner --------------------------------------------------------
app = App()
daemon_runner = MyDaemonRunner(app)
#This ensures that the logger file handle does not get closed during daemonization
daemon_runner.daemon_context.files_preserve=[lhandler.stream]
# Run daemon
daemon_runner.do_action()

