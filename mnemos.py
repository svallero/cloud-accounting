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
        self.pidfile_path = '/tmp/mnemos.pid' 
    
    def run(self):
        logger.info("**************************************")
        logger.info("*** Starting daemon mnemos.py      ***")
        logger.info("**************************************")
        print_config()       
        logger.info("--------------------------------------")
         
        # LOAD CLOUD PLUGIN
        logger.info('Loading cloud plugin...')
        try:
           # See: http://stackoverflow.com/questions/6677424/how-do-i-import-variable-packages-in-python-like-using-variable-variables-i
           cloud_plugin = getattr(__import__('plugins', fromlist=[ cloud_name ]), cloud_name)
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

        # MAIN LOOP
        while True:
            # Get accounting info
            val=cloud_plugin.get_accounting_data()
            
            insert=db_plugin.insert_accounting_data(val)

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
       global cloud_cf
       cloud_cf = cf_parser.items(cloud_name)
       global db_cf
       db_cf = cf_parser.items(db_name)

def print_config():
   # print configuration to logger 
   logger.info('CONFIGURATION:')
   logger.info('[mnemos]') 
   logger.info('   sleep_time='+str(sleep_time)+'') 
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


# Safely run a shell command --------------------------------------------------
def run_shell_cmd(command):
   try:
      proc = Popen(command, stdout=PIPE, stderr=PIPE, shell=True)
      out,err= proc.communicate()
      for outline in out.splitlines():
         logger.debug(outline)
      for errline in err.splitlines():
         logger.debug(errline)
   except:
      logger.error('Running command '+command+'')


# ENTRY POINT #
# Define daemon runner --------------------------------------------------------
app = App()
daemon_runner = MyDaemonRunner(app)
#This ensures that the logger file handle does not get closed during daemonization
daemon_runner.daemon_context.files_preserve=[lhandler.stream]
# Run daemon
daemon_runner.do_action()

