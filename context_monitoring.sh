#!/bin/sh

# Script to setup a VM with ES and Logstash.
# Configured to read accounting data from mnemos.
# Mailto: svallero@to.infn.it

BASE="/root"

# Important for "shellshock"
yum upgrade bash -y

# Install some package
PKG="java-1.7.0-openjdk firefox httpd git mod_ssl mysql rubygems"
GPKG="X Window System"
yum install $PKG -y
yum groupinstall "$GPKG" -y

# Elasticsearch
ESV="1.3.4"
ES="https://download.elasticsearch.org/elasticsearch/elasticsearch/elasticsearch-${ESV}.noarch.rpm -O ${BASE}/elasticsearch-${ESV}.noarch.rpm"
wget $ES
yum localinstall ${BASE}/elasticsearch-${ESV}.noarch.rpm -y
service elasticsearch start
rm ${BASE}/elasticsearch-${ESV}.noarch.rpm
# kopf plugin
/usr/share/elasticsearch/bin/plugin -install lmenezes/elasticsearch-kopf

# Logstash
# first get some ruby gem
#/usr/bin/gem install sequel ruby-mysql
# then get logstash
LSV="1.4.2"
LS="logstash-${LSV}"
wget https://download.elasticsearch.org/logstash/logstash/${LS}.tar.gz -O ${BASE}/${LS}.tar.gz
cd ${BASE}
gunzip ${BASE}/${LS}.tar.gz && tar -xvf ${BASE}/${LS}.tar
rm ${BASE}/${LS}.tar

# Get some custom stuff
wget https://raw.githubusercontent.com/PRIN-STOA-LHC/VafMonitoring/master/mysql.rb -O ${BASE}/${LS}/lib/logstash/inputs/mysql.rb
wget https://raw.githubusercontent.com/PRIN-STOA-LHC/VafMonitoring/master/production-template.json -O ${BASE}/${LS}/production-template.json

cat <<EOF > ${BASE}/configure_oneacct.conf
input {
     mysql {
         host => "srm-dom0.to.infn.it"
         port => 3306
         user => "sara"
         identifier => "xxx"
         database => "opennebula"
         tables => [joined,joined_summary]
         batch => 1
         type => "ONEACCT_logs"
         }
     }

output {
  elasticsearch {
         host => localhost
         index => "logstash-oneacct"
         template_overwrite => true
         template => "${BASE}/${LS}/production-template.json"
         }

  stdout { codec => rubydebug }
}

filter {
  date {
    match => [ "lastpolltime", "UNIX" ]
    target => "time_axis"
  }
  date {
    match => [ "timestamp", "UNIX" ]
    target => "time_axis"
  }
  mutate {
    convert => [ "val", "float" ]
  }
}
EOF

# this is required, else it complains it cannot find "sequel"...
${BASE}/${LS}/bin/plugin install contrib

# write a Logstash start script
LS_START="start_logstash.sh"
echo "${BASE}/${LS}/bin/logstash -f ${BASE}/configure_oneacct.conf --pluginpath ${BASE}/${LS}/lib/logstash/inputs/" > ${BASE}/${LS_START}

chmod +x ${BASE}/${LS_START}

 
# Apache
service iptables stop
setenforce 0
#afterburner script to set password
AF="afterburner.sh"
cat <<EOF > ${BASE}/${AF}
#!/bin/sh
htpasswd -c /etc/httpd/.htpasswd admin
EOF

chmod +x ${BASE}/${AF}

mv /etc/httpd/conf.d/ssl.conf /etc/httpd/conf.d/10ssl.conf
cat <<EOF > /etc/httpd/conf.d/20kibana.conf
<Directory "/var/www/html/kibana">
  AuthType Basic
  AuthName "Authentication Required"
  AuthUserFile "/etc/httpd/.htpasswd"
  Require valid-user
  SSLRequireSSL

  Order allow,deny
  Allow from all
</Directory>
EOF

service httpd start

# Kibana
cd /var/www/html/
git clone -b integral-support https://github.com/svallero/kibana.git
wget https://raw.githubusercontent.com/svallero/cloud-accounting/master/elk/Accounting_dashboard.json -O /var/www/html/kibana/src/app/dashboards/Accounting.json

# some fix for x11
dbus-uuidgen > /var/lib/dbus/machine-id

echo '***************************'
echo "Then run the afterburner!!!" 
echo '***************************'

