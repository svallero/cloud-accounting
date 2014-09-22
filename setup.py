# vi: ts=4 expandtab
#
#    Distutils magic for mnemos
#
#    Author: Sara Vallero <svallero@to.infn.it>
#    

from setuptools import setup

if __name__ == '__main__':

   ETC = '/etc'
   USR = '/usr'

   setup(
      name='mnemos',
      version='0.0.0',
      description='Handle dynamic quotas within cloud.',
      author='Sara Vallero',
      author_email='svallero@to.infn.it',
      url='https://github.com/svallero/cloud-accounting',
      packages = [ 'mnemos' ],      
      include_package_data = True,
      scripts=['mnemos/bin/mnemos',
               'mnemos/mnemos_publisher.py',
               'mnemos/mnemos_receiver.py',  
               ],
      data_files=[(ETC + '/mnemos', 'mnemos/etc/*.cfg'),
                 ],
      # Dependencies
     install_requires = [
        'pika',
        'python-daemon'
     ]
   )
