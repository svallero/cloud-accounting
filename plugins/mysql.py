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
  

def get_quotas():
   import  MySQLdb
   from MySQLdb import connect
   retval={}
   # connect to database
   try:
      db = connect(db=database, user=user,passwd=password, host=host, port=int(port))
      cur = db.cursor()
      cur.execute("select * from quotas")
      retval=cur.fetchall()
      #print "retval=",retval
   except Exception as err:
      logger.error('MYSQL - ERROR: get_quotas')
      return 1

   # if everything went fine...
   return retval
         
def get_summary(username,starttime):
   import  MySQLdb
   from MySQLdb import connect
   retval={}
   values={} 
   # connect to database
   try:
      db = connect(db=database, user=user,passwd=password, host=host, port=int(port))
      cur = db.cursor()
      # select last entry for each vm (in terms of polltime)
      # only those that where last polled or stopped 
      cur.execute('''select j.vmid, j.starttime, j.lastpolltime, j.stoptime, j.cpus, j.memory, j.disksize from (select vmid,max(lastpolltime) as maxpolltime from joined group by vmid) as x inner join joined as j on j.vmid = x.vmid and j.lastpolltime = x.maxpolltime where username=%s and (lastpolltime > %s or stoptime > %s)''', (username,starttime,starttime))
      values=cur.fetchall()
   except Exception as err:
      logger.error('MYSQL - ERROR: get_summary')
      return 1

   # summing-up
   # stop time for summary is latest poll time
   stoptime=0
   cputime=0
   memtime=0
   disktime=0
   for val in values:
      vmstart=val[1]
      vmpoll=val[2] 
      if vmpoll > stoptime:
         stoptime = vmpoll  
      vmstop=val[3]
      cpu=val[4]
      mem=val[5]
      disk=val[6]
      # start time for integral
      if starttime > vmstart:
         start = starttime
      else:
         start = vmstart
      # stop time for integral
      if vmstop:
         stop = vmstop
      else:
         stop = vmpoll
      period=stop-start
      if period < 0:
         print '*** DEBUG period is < 0 !!! ***'
      cputime += (cpu*period)
      if username=='svallero': 
         print val[0],cpu*period
      memtime += (mem*period)
      disktime += (disk*period)
   
   nvms=len(values)
   # if everything went fine...
   retval={'user': username, 'start': starttime, 'stop': stoptime, '#vms': nvms, 'memory-time': memtime, 'cpu-time': cputime, 'disk-time': disktime}
   return retval
    

def insert_accounting_data(values):
  import  MySQLdb
  from MySQLdb import connect
  
  try:
     # connect to database
     db = connect(db=database, user=user,passwd=password, host=host, port=int(port))
     cur = db.cursor()
     # VMS TABLE
     # check if vm is already there and on the same host 
     # (this is to account for migrated vms as separate entries)
     #print values['id'], values['host']
     cur.execute("select * from vms where vmid=%s and host=%s", (values['id'], values['host'])) 
     #print cur.rowcount, values['id']

     if not cur.rowcount:
        cur.execute('''insert into vms values (0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s )''', (values['id'],values['name'], values['username'], values['groupname'],values['cpus'],values['memory'],values['host'],values['image'],values['ndisks'],values['disksize'],values['starttime']))
  
     # HISTORY TABLE
     # select last entry for given vm 
     try:
        cur.execute("select lastpolltime, stoptime from history where vmid=%s and host=%s ORDER BY lastpolltime DESC limit 1", (values['id'], values['host'])) 
        tmp=cur.fetchall()[0]
     except Exception as err:
        tmp=0 

     if not tmp:
        # if there is no previous entry...
        last_lastpolltime=values['starttime'] #WRONG THIS SHOULD BE STARTTIME
        last_stoptime=0
        #deltat=values['stoptime']-values['lastpolltime'] # here starttime-stoptime or starttime-polltime
        #if deltat < 0:
        #   deltat=0   
     else:
        last_lastpolltime=tmp[0]
        last_stoptime=tmp[1]
     if values['stoptime'] == 0:
        deltat=values['lastpolltime']-last_lastpolltime
     else:
        deltat=values['stoptime']-last_lastpolltime
     # if vm was not stopped last time we checked...
     if  last_stoptime == 0 and values['lastpolltime'] != last_lastpolltime:
        # insert 
        cur.execute('''insert into history values (0,%s,%s,%s,%s,%s,%s,%s)''', (values['id'],values['host'], values['lcmstate'], values['lastpolltime'],values['stoptime'],deltat, values['timestamp']))
  except Exception as err:
     logger.error('MYSQL - ERROR: insert_accounting_data -> '+str(err)+'')
     return 1 

  # if everything went fine...
  return 0


def insert_summary_data(values):
  import  MySQLdb
  from MySQLdb import connect
  
  try:
     # connect to database
     db = connect(db=database, user=user,passwd=password, host=host, port=int(port))
     cur = db.cursor()
     # QUOTAS TABLE
     # check if quota or starttime has changed 
     cur.execute("select * from quotas where starttime=%s and maxcputime=%s", [values['starttime'], values['maxcputime']]) 

     if not cur.rowcount:
        cur.execute('''insert into quotas values (0,%s,%s,%s)''', (values['user'],values['starttime'], values['maxcputime']))

     #return 0
     # SUMMARY TABLE
     # select last quota for given user 
     cur.execute('''select qid from quotas where username=%s order by qid desc limit 1''',  [values['user']]) 
     tmp=cur.fetchall()[0]

     # insert
     vars=('maxcputime','cputime','memorytime','disktime','nvms') 
     for var in vars:
        #logger.info(''+str(tmp[0])+''+str(values['stoptime'])+' '+var+' '+str(values[var])+'')
        cur.execute('''insert into summary values (0,%s,%s,%s,%s)''', (tmp[0],values['stoptime'], var, values[var]))
     # plus some other useful var
     left=values['maxcputime']-values['cputime']
     cur.execute('''insert into summary values (0,%s,%s,%s,%s)''', (tmp[0],values['stoptime'], 'left', left))
     mean_cputime=values['cputime']/(values['stoptime']-values['starttime']) 
     cur.execute('''insert into summary values (0,%s,%s,%s,%s)''', (tmp[0],values['stoptime'], 'mean_cputime', mean_cputime))
     mean_maxcputime=values['maxcputime']/(365*86400)
     cur.execute('''insert into summary values (0,%s,%s,%s,%s)''', (tmp[0],values['stoptime'], 'mean_maxcputime', mean_maxcputime))
  except Exception as err:
     logger.error('MYSQL - ERROR: insert_summary_data -> '+str(err)+'')
     return 1 

  # if everything went fine...
  return 0



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

