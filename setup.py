# vi: ts=4 expandtab
#
#    Distutils magic for mnemos
#
#    Author: Sara Vallero <svallero@to.infn.it>
#    

from glob import glob
from setuptools import setup
#from setuptools.command.install import install

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
      packages = [ 'mnemos', ],      
      #packages = find_packages(),      
      scripts=['mnemos/bin/mnemos',
               'mnemos/mnemos_publisher.py',
               'mnemos/mnemos_receiver.py',  
               ],
      data_files=[(ETC + '/mnemos', glob('mnemos/etc/*.cfg')),
                 ],
      include_package_data = True,
      #py_modules = ['mnemos'],

      # Dependencies
     install_requires = [
        'pika',
        'python-daemon'
     ]
   )
