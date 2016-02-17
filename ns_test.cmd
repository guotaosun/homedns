
@echo off

cls
set SERVER=%1
set OLD_PROMPT=%PROMPT%
set PROMPT=$G

echo ===============
echo HomeDNS testing
echo ===============
echo on

@echo off
echo --------------
echo test subdomain
echo --------------
echo on
nslookup ldap.mylocal.home %SERVER%
nslookup -type=ns mylocal.home %SERVER%
nslookup -type=mx mylocal.home %SERVER%
nslookup -type=soa mylocal.home %SERVER%

@echo off
echo ------------------
echo test hosts.homedns
echo ------------------
echo on
nslookup unknown.cisco.com %SERVER%

@echo off
echo ---------------
echo test white list
echo ---------------
echo on
nslookup www.cisco.com %SERVER%

@echo off
echo ---------------
echo test black list
echo ---------------
echo on
nslookup www.google.com %SERVER%

@echo off
echo ---------------
echo test TXT record
echo ---------------
echo on
nslookup -type=txt mylocal.home %SERVER%

@echo off
echo ---------------------
echo test local SRV record
echo ---------------------
echo on
nslookup -type=srv _ldap._tcp %SERVER%

@echo off
echo ----------------------
echo test remote SRV record
echo ----------------------
echo will be change to local domain
echo on
nslookup -type=srv _ldap._tcp.cisco.com %SERVER%

@echo off
set PROMPT=%OLD_PROMPT%
