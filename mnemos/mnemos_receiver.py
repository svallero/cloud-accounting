#!/usr/bin/python

###############################################################################
#                                                                             #
# Daemon to backup accounting data in dedicated DB                            #
# and take action if quotas are exceeded.                                     #
#                                                                             #
# The DB is structured in a way to be easily read by Logstash.                #
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
# python mnemos.py start                                                      # 
#                                                                             #
# Init script: TODO                                                           #
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
import pwd
import pika
import smtplib
from email.mime.text import MIMEText
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
        self.pidfile_path = '/var/run/mnemos/mnemos_receiver.pid' 
    
    def run(self):
        logger.info("**************************************")
        logger.info("*** Starting daemon mnemos.py      ***")
        logger.info("**************************************")
        print_config()       
        logger.info("--------------------------------------")
        
        # LOAD DB PLUGIN
        logger.info('Loading database plugin...')
        global db_plugin
        try:
           db_plugin = getattr(__import__('plugins', fromlist=[ db_name ]), db_name)
        except (ImportError, AttributeError) as e:
           logger.fatal('Cannot find database plugin: '+db_name+'')
           sys.exit(2)

        logger.info('Loaded database plugin: '+db_name+'')

        # Init db plugin
        logger.info('Init database plugin...')
        db_plugin.init(db_cf,logger)
        logger.info("**************************************")

        # Initialize connection to RabbitMQ
        global connection
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        global channel
        channel=connection.channel() 
        # add a time-out after which you stop consuming (5 min)
        # at next loop you start consuming again
        # this is to allow re-processing of failed message deliveries (mainly to database) 
        connection.add_timeout(300, on_timeout)

        # MAIN LOOP
        while True:
            channel.basic_consume(mnemos_callback,queue='mnemos',no_ack=False)
            channel.basic_consume(alarms_callback,queue='alarms',no_ack=False)
            channel.basic_consume(summary_callback,queue='summary',no_ack=False)
            channel.basic_consume(summarydb_callback,queue='summary_db',no_ack=False)
            logger.info('Start consuming...')  
            channel.start_consuming() # this never exits...


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
       global logfile
       logfile=''+logdir+'/mnemos_receiver.log'
       global db_cf
       db_cf = cf_parser.items(db_name)

def print_config():
   # print configuration to logger 
   logger.info('CONFIGURATION:')
   logger.info('[mnemos]') 
   logger.info('   sleep_time='+str(sleep_time)+'') 
   logger.info('   logdir='+logdir+'')
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


# Rabbit stuff ----------------------------------------------------------------
def mnemos_callback(ch, method, properties, body):
    payload=ast.literal_eval(body)
    insert=db_plugin.insert_accounting_data(payload)
    if not insert:
       logger.debug('[mnemos] Processed %r' % (body,))
       channel.basic_ack(delivery_tag = method.delivery_tag)

def summarydb_callback(ch, method, properties, body):
    payload=ast.literal_eval(body)
    insert=db_plugin.insert_summary_data(payload)
    if not insert:
       logger.debug('[summary_db] Processed %r' % (body,))
       channel.basic_ack(delivery_tag = method.delivery_tag)
    

def alarms_callback(ch, method, properties, body):
    error=0
    try:
       msg = MIMEText(body)
       msg['Subject'] = 'MNEMOS: quota exceeded!'
       msg['From'] = mail_sender
       msg['To'] = mail_receiver
 

       receiver = mail_receiver.split(',')      
       # Send the message via our own SMTP server, but don't include the
       # envelope header.
       s = smtplib.SMTP('localhost')
       #s.sendmail(mail_sender, receiver, msg.as_string())
       s.quit()
    except: 
       error=1
    if not error:
       logger.info('[alarms] Processed %r' % (body,))
       channel.basic_ack(delivery_tag = method.delivery_tag)

def summary_callback(ch, method, properties, body):
    logger.info('[summary] Received %r' % (body,))
    channel.basic_ack(delivery_tag = method.delivery_tag)
  
def on_timeout():
  channel.stop_consuming()
  logger.info('Stop consuming...')

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

