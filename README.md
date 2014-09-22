Cloud Accounting
===========

Backup accounting data in MySQL DB suited for Logstash.
Handle dynamic quotas.

PRE-REQUISITES:

On your server you should have installed:

- MySQL (configure a user with create + insert privileges that will be used by Mnemos)
- rabbitmq-server

You also need to have installed the package "MySQL-python", i.e. on CentOS: 

- yum install MySQL-python --enablerepo=epel

INSTALL

The python way (as root, though the daemons will run as unprivileged user "mnemos"):

- python setup.py install

The rpm way:

- yum install rpm-build
- python setup.py bdist --format=rpm

You can find you rpm in dist, so you can install it, i.e.:
- yum localinstall dist/mnemos-0.0.0-1.noarch.rpm

RUN

- mnemos start|stop|status
- or add /usr/bin/mnemos to your start-up scripts (i.e. in /etc/init.d/)


