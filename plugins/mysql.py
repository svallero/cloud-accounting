#######################################
#                                     #
# MySQL plugin for mnemos             #
#                                     # 
# mailto: svallero@to.infn.it         #
#                                     #
#######################################



def init(cf_plugin,logging):
  # Initializes the plugin
  global logger
  logger=logging
  logger.info('MYSQL - Configuring plugin...')
  configure(cf_plugin) 
  logger.info('MYSQL - Plugin initialized!')

def insert_accounting_data(val):
  import  MySQLdb
  from MySQLdb import connect
  
  # connect to database
  db = connect(db=database, user=user,passwd=password, host=host, port=int(port))
  cur = db.cursor()
  for v in val.items():
     values=v[1]
     # VMS TABLE
     # check if vm is already there and on the same host 
     # (this is to account for migrated vms as separate entries)
     cur.execute("select * from vms where vmid=%s and host=%s", (values['id'], values['host'])) 

     if not cur.rowcount:
        cur.execute('''insert into vms values (0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s )''', (values['id'],values['name'], values['username'], values['groupname'],values['cpus'],values['memory'],values['host'],values['image'],values['ndisks'],values['disksize'],values['starttime']))
     
     # HISTORY TABLE
     # select last entry for given vm 
     try:
        cur.execute("select lastpolltime, stoptime from history where vmid=%s and host=%s ORDER BY lastpolltime DESC limit 1", (values['id'], values['host'])) 
        tmp=cur.fetchall()[0]
     except Exception as err:
        #print str(err)
        tmp=0 

     if not tmp:
        # if there is no previous entry...
        last_lastpolltime=values['starttime']
        last_stoptime=0
     else:
        last_lastpolltime=tmp[0]
        last_stoptime=tmp[1]
     # if vm was not stopped last time we checked...
     if  last_stoptime == 0 and values['lastpolltime'] != last_lastpolltime:
        if values['stoptime'] == 0:
           deltat=values['lastpolltime']-last_lastpolltime
        else:
           deltat=values['stoptime']-last_lastpolltime
        # insert 
        cur.execute('''insert into history values (0,%s,%s,%s,%s,%s,%s)''', (values['id'],values['host'], values['lcmstate'], values['lastpolltime'],values['stoptime'],deltat))





def configure(config_file):
   if not config_file:
      logger.error('MYSQL - Configuration not specified!')
   else:
      logger.debug('MYSQL - Reading configuration from file...')
      logger.info('[mysql]')
      for key,val in config_file: 
         globals() [key]=val
         if 'password' in key:
            pval= 'xxx'
         else:
            pval=val
         logger.info('   '+key+'='+pval+'')   

