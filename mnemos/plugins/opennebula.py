#######################################
#                                     #
# OpenNebula plugin for mnemos        #
#                                     # 
# mailto: svallero@to.infn.it         #
#                                     #
#######################################



def init(cf_plugin,logging):
  # Initializes the plugin
  global logger
  logger=logging
  logger.info('OPENNEBULA - Configuring plugin...')
  configure(cf_plugin) 
  logger.info('OPENNEBULA - Plugin initialized!')

def get_accounting_data(now):
   retval={}
   import xmlrpclib
   import os
   import time
   from lxml import objectify
   # connect to endpoint
   server=xmlrpclib.ServerProxy(endpoint)
   # get accounting information (oneacct)
   acct=server.one.vmpool.accounting(auth,-2,-1,-1)
   #acct=server.one.vmpool.accounting(auth,47,-1,-1)
   entries=objectify.fromstring(acct[1])   
   ne=-1 # to count entries 
   for e in entries.HISTORY:
      ne += 1
      # get vm id (this should never be null)
      id = e.VM.ID
      # get name 
      name = '-'
      if hasattr(e.VM,'NAME'):
         name = e.VM.NAME
      # get username (this should never be null)
      username = e.VM.UNAME
      # get groupname (this should never be null)
      groupname = e.VM.GNAME
      # get number of cpus
      cpus = 0
      if hasattr(e.VM.TEMPLATE,'CPU'):
         cpus=e.VM.TEMPLATE.CPU
      elif hasattr(e.VM.TEMPLATE,'VCPU'):
         cpus=e.VM.TEMPLATE.VCPU
      # get allocated memory  
      mem = 0
      if hasattr(e.VM.TEMPLATE,'MEMORY'):
         mem = e.VM.TEMPLATE.MEMORY
      # get host (this should never be null)
      host = e.HOSTNAME
      # get ephemeral disks and image name of disk 0
      ndisks=0
      tot_disk_size=0
      image = '-'
      if hasattr(e.VM.TEMPLATE,'DISK'):
         for disk in e.VM.TEMPLATE.DISK:
            if not hasattr(disk,'DISK_ID'):
               continue
            elif disk.DISK_ID == 0:
               if hasattr(disk,'IMAGE'):
                  image = disk.IMAGE
            else:
               if not (hasattr(disk,'PERSISTENT') and disk.PERSISTENT):
                  ndisks+=1
                  if hasattr(disk,'SIZE'):
                     tot_disk_size+=disk.SIZE
      else:
         logger.debug('VM '+str(id)+' - ERROR no disk!')
         # get start/stop time

      start_time = e.STIME
      stop_time = e.ETIME
      # get lcm state
      lcm_state = e.VM.LCM_STATE
      # get last poll time
      last_poll_time = e.VM.LAST_POLL
      if last_poll_time == 0:
         # something went wrong...
         stop_time=1 # to avoid inserting in db over and over...  
      #print vars(e.VM)
      retval[ne]={'id': id, 'name': name, 'username': username, 'groupname': groupname, 'cpus': cpus, 'memory': mem, 'host': host, 'image': image, 'ndisks': ndisks, 'disksize': tot_disk_size, 'starttime': start_time, 'lcmstate': lcm_state, 'lastpolltime': last_poll_time, 'stoptime': stop_time, 'timestamp': now}

   return retval


# Configuration ---------------------------------------------------------------
def configure(config_file):
   if not config_file:
      logger.error('OPENNEBULA - Configuration not specified!')
   else:
      logger.debug('OPENNEBULA - Reading configuration from file...')
      logger.info('[opennebula]')
      for key,val in config_file: 
         globals() [key]=val
         if 'auth' in key:
            pval= ''+val.split(':')[0]+':xxx'
         else:
            pval=val
         logger.info('   '+key+'='+pval+'')   

