#!/usr/bin/env python
# -*- encoding:utf-8 -*-

version = '0.1.12'


class defaults():
    log = {
        'file': 'homedns.log',
        'level': 30,
    }
    server = {
        # local listen on 'tcp', 'udp'
        'protocols': ['udp'],
        # local listen ip
        'listen_ip': '127.0.0.1',
        # local listen port
        'listen_port': 53,
        # search domain from 'local' or 'upstream'
        'search': ['local', 'upstream'],
        # allowed hosts to access
        # 192.168.1.0/24, 192.168.2.10-100, 192.168.3.*, 192.168.*.*
        'allowed_hosts': ['127.0.0.1'],
    }
    smartdns = {
        # match rule by order in list.
        'rules': [
            ['black', {
                'url': 'https://github.com/liuyug/homedns/raw/master/black.rules',
                'proxy': False,
                # 60 * 60 * 8
                'refresh': 28800,
            }],
            ['default', {
                'url': 'default.rules',
                'proxy': False,
                # 60 * 60 * 8
                'refresh': 28800,
            }],
        ],
        'hack_srv': ['_ldap._tcp'],
        'proxy': {
            # proxy type: SOCKS5, SOCKS4 or HTTP
            'type': 'SOCKS5',
            # proxy ip
            'ip': '127.0.0.1',
            # proxy port
            'port': 1080,
        },
        # upstream dns server
        'upstreams': [
            {
                'ip': '114.114.114.114',
                'port': 53,
                'timeout': 5,
                'rule': 'default',
                'proxy': False,
            },
            {
                'ip': '114.114.115.115',
                'port': 53,
                'timeout': 5,
                'rule': 'default',
                'proxy': False,
            },
            {
                'ip': '8.8.8.8',
                'port': 53,
                'timeout': 5,
                'rule': 'black',
                'proxy': True,
            },
            {
                'ip': '8.8.4.4',
                'port': 53,
                'timeout': 5,
                'rule': 'black',
                'proxy': True,
            },
        ],
    }
    domains = [
        {
            'name': 'mylocal.home',
            'url': 'mylocal.home.json',
            'proxy': False,
            'type': 'dns',
            # 60 * 60 * 8
            'refresh': 28800,
        },
        {
            'name': 'hosts.homedns',
            'url': 'hosts.homedns',
            'proxy': False,
            'type': 'hosts',
            # 60 * 60 * 8
            'refresh': 28800,
        },
    ]
    mylocal_home = {
        # dns NS record
        'NS': ['ns1', 'ns2'],
        # dns MX record
        'MX': ['mail'],
        # dns SOA record
        'SOA': {
            # primary dns server
            'mname': 'ns1',
            # dns contact email address. '@' is replaced by '.'
            'rname': 'admin',
            'serial': 20160101,
            # 60 * 60 * 1
            'refresh': 3600,
            # 60 * 60 * 3
            'retry': 10800,
            # 60 * 60 * 24
            'expire': 86400,
            # 60 * 60 * 1
            'minimum': 3600,
        },
        # dns A record. ipv4
        'A': {
            # '@' is current domain
            '@': ['127.0.0.1'],
            # MX and NS domain name must be A record
            'ns1': ['127.0.0.1'],
            'ns2': ['127.0.0.1'],
            'mail': ['127.0.0.1'],
        },
        # dns A record. ipv6
        'AAAA': {
            '@': ['::1'],
            'ns1': ['::1'],
            'ns2': ['::1'],
            'mail': ['::1'],
        },
        # dns CNAME record. alias domain.
        'CNAME': {
            'www': ['@'],
            'ldap': ['www'],
            'kms': ['www'],
        },
        # dns TXT record
        'TXT': {
            'fun': ['happy!'],
            'look': ['where?'],
            '@': ['my home', 'my domain'],
        },
        # dns SRV record
        'SRV': {
            '_ldap._tcp': ['0 100 389 ldap'],
            '_vlmcs._tcp': ['0 100 1688 kms'],
        },
        'PTR': {
            '127.0.0.2': ['@'],
            '::2': ['@'],
        },
    }


def init():
    global config
    global local_domains
    global allowed_hosts
    global rules
    global config_dir
