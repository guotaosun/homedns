#!/usr/bin/env python
# -*- encoding:utf-8 -*-

import datetime
import os.path
import time
import threading
import binascii
import logging
import argparse
import json
import socket
import struct
import traceback
from collections import OrderedDict
try:
    # py3
    import socketserver
    from queue import Queue
except:
    # py2
    import SocketServer as socketserver
    from Queue import Queue

import socks
import netaddr
from dnslib import RR, QTYPE, DNSRecord, DNSHeader, DNSLabel

from .domain import Domain, HostDomain
from .adblock import Adblock
from .loader import TxtLoader, JsonLoader
from .iniconfig import ini_read, ini_write
from . import globalvars


logger = logging.getLogger(__name__)


class BaseRequestHandler(socketserver.BaseRequestHandler):

    def get_data(self):
        raise NotImplementedError

    def send_data(self, data):
        raise NotImplementedError

    def handle(self):
        logger.info('%s REQUEST %s' % ('=' * 35, '=' * 36))
        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')
        client_ip = self.client_address[0]
        client_port = self.client_address[1]
        logger.warn("%s request %s (%s %s):" % (
            self.__class__.__name__[:3],
            now,
            client_ip, client_port,
        ))
        if client_ip not in globalvars.allowed_hosts:
            logger.warn('\t*** Not allowed host: %s ***' % client_ip)
            return
        try:
            data = self.get_data()
            logger.info('%s %s' % (len(data), binascii.b2a_hex(data)))
            dns_response(self, data)
        except Exception as err:
            traceback.print_exc()
            logger.fatal('send data: %s' % (err))


class TCPRequestHandler(BaseRequestHandler):

    def get_data(self):
        data = self.request.recv(8192).strip()
        sz = int(binascii.b2a_hex(data[:2]), 16)
        if sz < len(data) - 2:
            raise Exception("Wrong size of TCP packet")
        elif sz > len(data) - 2:
            raise Exception("Too big TCP packet")
        return data[2:]

    def send_data(self, data):
        sz = bytes(binascii.a2b_hex(hex(len(data))[2:].zfill(4)))
        return self.request.sendall(sz + data)


class UDPRequestHandler(BaseRequestHandler):

    def get_data(self):
        return self.request[0].strip()

    def send_data(self, data):
        return self.request[1].sendto(data, self.client_address)


def lookup_local(handler, request):
    qn2 = qn = request.q.qname
    qt = QTYPE[request.q.qtype]

    reply = DNSRecord(
        DNSHeader(id=request.header.id, qr=1, aa=1, ra=1),
        q=request.q
    )

    is_local = False
    for value in globalvars.local_domains.values():
        domain = value['domain']
        if globalvars.config['smartdns']['hack_srv'] and qt == 'SRV' and \
                not domain.inDomain(qn2):
            r_srv = b'.'.join(qn.label[:2])
            if r_srv.decode().lower() in globalvars.config['smartdns']['hack_srv']:
                qn2 = DNSLabel(domain.get_subdomain('@')).add(r_srv)
                logger.warn('\tChange SRV request to %s from %s' % (qn2, qn))

        if domain.inDomain(qn2):
            is_local = True
            rr_data = domain.search(qn2, qt)
            for r in rr_data:
                answer = RR(
                    rname=qn,
                    rtype=getattr(QTYPE, r['type']),
                    rclass=1, ttl=60 * 5,
                    rdata=r['rdata'],
                )
                reply.add_answer(answer)
            if reply.rr:
                break

    if is_local:
        if reply.rr:
            lines = []
            for r in reply.rr:
                rqn = r.rdata
                rqt = QTYPE[r.rtype]
                lines.append('\t\t%s(%s)' % (rqn, rqt))
            logger.warn('\tFrom LOCAL return:\n%s' % '\n'.join(lines))
            logger.info(reply)
        else:
            logger.warn('\tFrom LOCAL return: N/A')
        handler.send_data(reply.pack())
    return is_local


def do_lookup_upstream(data, dest, port=53,
                       tcp=False, timeout=None, ipv6=False,
                       proxy=None):
    """
        Send packet to nameserver and return response through proxy
        proxy_type: SOCKS5, SOCKS4, HTTP

        Note:: many proxy server only support TCP mode.
    """
    def get_sock(inet, tcp, proxy=None):
        stype = socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM
        if tcp and proxy:
            sock = socks.socksocket(inet, stype)
            sock.set_proxy(
                socks.PROXY_TYPES[proxy['type'].upper()],
                proxy['ip'],
                proxy['port'],
            )
            message = '\tForward to server %s:%s with TCP mode' % (dest, port)
            message += ' and proxy %(type)s://%(ip)s:%(port)s' % proxy
            logger.warn(message)
        else:
            sock = socket.socket(inet, stype)
            message = '\tForward to server %s:%s with %s mode' % (
                dest, port,
                'TCP' if tcp else 'UDP',
            )
            logger.warn(message)
        return sock

    if ipv6:
        inet = socket.AF_INET6
    else:
        inet = socket.AF_INET

    sock = get_sock(inet, tcp, proxy)
    if tcp:
        if len(data) > 65535:
            raise ValueError("Packet length too long: %d" % len(data))
        data = struct.pack("!H", len(data)) + data
        if timeout is not None:
            sock.settimeout(timeout)
        sock.connect((dest, port))
        sock.sendall(data)
        response = sock.recv(8192)
        length = struct.unpack("!H", bytes(response[:2]))[0]
        while len(response) - 2 < length:
            response += sock.recv(8192)
        sock.close()
        response = response[2:]
    else:
        if timeout is not None:
            sock.settimeout(timeout)
        sock.sendto(data, (dest, port))
        response, server = sock.recvfrom(8192)
        sock.close()
    return response


def lookup_upstream_worker(queue, server, proxy=None):
    """
    use TCP mode when proxy enable
    """
    while True:
        handler, request = queue.get()
        try:
            r_data = do_lookup_upstream(
                request.pack(),
                server['ip'],
                server['port'],
                tcp=server['proxy'],
                timeout=server['timeout'],
                proxy=proxy,
            )
            reply = DNSRecord.parse(r_data)
            if reply.rr:
                lines = []
                for r in reply.rr:
                    rqn = r.rdata
                    rqt = QTYPE[r.rtype]
                    lines.append('\t\t%s(%s)' % (rqn, rqt))
                logger.warn('\tFrom %s:%s return:\n%s' % (
                    server['ip'], server['port'],
                    '\n'.join(lines)
                ))
                logger.info(reply)
                handler.send_data(reply.pack())
        except Exception as err:
            if logger.isEnabledFor(logging.DEBUG):
                traceback.print_exc()
            logger.fatal('\tError when lookup from %s:%s: %s' % (
                server['ip'], server['port'],
                err,
            ))
        queue.task_done()


def dns_response(handler, data):
    try:
        request = DNSRecord.parse(data)
    except Exception as err:
        logger.error('Parse request error: %s' % err)
        return
    qn = request.q.qname
    qt = QTYPE[request.q.qtype]
    logger.warn('\tRequest: %s(%s)' % (qn, qt))
    logger.info(request)

    local = False
    if 'local' in globalvars.config['server']['search']:
        local = lookup_local(handler, request)
    if not local and 'upstream' in globalvars.config['server']['search']:
        qn2 = str(qn).rstrip('.')
        for name, param in globalvars.rules.items():
            if param['rule'].isBlock(qn2):
                logger.warn('\tRequest(%s) is in "%s" list.' % (qn, name))
                for value in param['upstreams']:
                    value['queue'].put((handler, request))
                    value['count'] += 1
                break
    # update
    for value in globalvars.rules.values():
        rule = value['rule']
        if rule.isNeedUpdate(value['refresh']):
            rule.async_update()
    for value in globalvars.local_domains.values():
        domain = value['domain']
        if domain.isNeedUpdate(value['refresh']):
            domain.async_update()


def init_config(args):
    globalvars.init()

    fsplit = os.path.splitext(args.config)
    ini_file = fsplit[0] + '.ini'
    json_file = fsplit[0] + '.json'
    ext = fsplit[1].lower()
    if os.path.exists(args.config):
        if ext == '.ini':
            globalvars.config = ini_read(args.config)
        elif ext == '.json':
            globalvars.config = json.load(open(args.config))
        else:
            raise TypeError('Unknown config file: %s' % args.config)
    else:
        globalvars.config = {
            'log': globalvars.defaults.log,
            'server': globalvars.defaults.server,
            'smartdns': globalvars.defaults.smartdns,
            'domains': globalvars.defaults.domains,
        }
    if not os.path.exists(ini_file):
        ini_write(globalvars.config, ini_file)
    if not os.path.exists(json_file):
        json.dump(globalvars.config, open(json_file, 'w'), indent=4)
    globalvars.config_dir = os.path.abspath(os.path.dirname(args.config))
    globalvars.log_dir = globalvars.config_dir

    log_level = globalvars.config['log']['level']
    if args.verbose >= 0:
        log_level = logging.WARNING - (args.verbose * 10)

    if log_level <= logging.DEBUG:
        formatter = '[%(name)s %(lineno)d] %(message)s'
    else:
        formatter = '%(message)s'

    if args.verbose >= 0:
        logging.basicConfig(
            format=formatter,
            level=log_level,
        )
    else:
        log_file = os.path.join(
            globalvars.log_dir,
            globalvars.config['log']['file']
        )
        logging.basicConfig(
            filename=log_file,
            format=formatter,
            level=log_level
        )

    logger.error('HomeDNS v%s' % globalvars.version)
    logger.error('Config Dir: %s' % globalvars.config_dir)

    proxy = globalvars.config['smartdns']['proxy']

    # upstream dns server
    upstreams = globalvars.upstreams = {}
    for name, value in globalvars.config['smartdns']['upstreams'].items():
        q = Queue()
        t = threading.Thread(
            target=lookup_upstream_worker,
            args=(q, value),
            kwargs={
                'proxy': proxy if value['proxy'] else None
            }
        )
        t.daemon = True
        t.start()
        upstreams[name] = {
            'queue': q,
            'thread': t,
            'count': 0,
        }

    # rules
    globalvars.rules = OrderedDict()
    for value in globalvars.config['smartdns']['rules']:
        name = value['name']
        loader = TxtLoader(
            value['url'],
            proxy=proxy if value['proxy'] else None,
        )
        if loader.local and not os.path.exists(loader.url):
            if name == 'default' and value['url'] == 'default.rules':
                with open(loader.url, 'w') as f:
                    f.write('! Generated by HomeDNS v%s\n' % globalvars.version)
                    f.write('! match all domains\n')
                    f.write('*.*\n')
            else:
                raise OSError('Not found Rule %s: %s' % (
                    name,
                    loader.url,
                ))
        logger.error('Add rules %s - %s' % (name, loader))
        ab = Adblock(name)
        ab.create(loader)
        globalvars.rules[name] = {
            'rule': ab,
            'upstreams': [upstreams[dns] for dns in value['dns'] if dns in upstreams],
            'refresh': value['refresh'],
        }

    # allowed hosts
    globalvars.allowed_hosts = netaddr.IPSet()
    for hosts in globalvars.config['server']['allowed_hosts']:
        if '*' in hosts or '-' in hosts:
            globalvars.allowed_hosts.add(netaddr.IPGlob(hosts))
        elif '/' in hosts:
            globalvars.allowed_hosts.add(netaddr.IPNetwork(hosts))
        else:
            globalvars.allowed_hosts.add(hosts)

    # local domains
    globalvars.local_domains = {}
    for domain in globalvars.config['domains']:
        if domain['type'] == 'hosts':
            loader = TxtLoader(
                domain['url'],
                proxy=proxy if domain['proxy'] else None,
            )
            if loader.local and not os.path.exists(loader.url):
                if domain['name'] == 'hosts.homedns' and domain['url'] == 'hosts.homedns':
                    with open(loader.url, 'w') as f:
                        f.write('# Generated by HomeDNS v%s\n' % globalvars.version)
                        for host in globalvars.defaults.hosts_homedns:
                            f.write('%(ip)s\t%(name)s\n' % host)
                else:
                    raise OSError('Not found Domain %s: %s' % (
                        domain['name'],
                        loader.url,
                    ))
            d = HostDomain(domain['name'])
            d.create(loader)
        elif domain['type'] == 'dns':
            loader = JsonLoader(
                domain['url'],
                proxy=proxy if domain['proxy'] else None,
            )
            if loader.local and not os.path.exists(loader.url):
                if domain['name'] == 'mylocal.home' and domain['url'] == 'mylocal.home.json':
                    json.dump(
                        globalvars.defaults.mylocal_home,
                        open(loader.url, 'w'),
                        indent=4,
                    )
                else:
                    raise OSError('Not found Domain %s: %s' % (
                        domain['name'],
                        loader.url,
                    ))
            d = Domain(domain['name'])
            d.create(loader)
        logger.error('Add domain %s - %s' % (domain['name'], loader))
        globalvars.local_domains[domain['name']] = {
            'domain': d,
            'refresh': domain['refresh'],
        }


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', action='version',
                        version='%%(prog)s %s' % globalvars.version)
    parser.add_argument('-v', '--verbose', help='verbose help',
                        action='count', default=-1)
    parser.add_argument(
        '--config',
        help='read config from file',
        default='homedns.ini',
    )
    args = parser.parse_args()

    init_config(args)

    logger.debug('Config: %s', globalvars.config)
    for value in globalvars.local_domains.values():
        domain = value['domain']
        logger.debug('Domain "%s" records:' % domain)
        domain.output_records(logger.debug)
    for value in globalvars.rules.values():
        ab = value['rule']
        logger.debug('Rule "%s":' % ab)
        ab.output_list(logger.debug)

    logger.error("Starting nameserver...")

    ip = globalvars.config['server']['listen_ip']
    port = globalvars.config['server']['listen_port']

    logger.error('Listen on %s:%s' % (ip, port))

    servers = []
    if 'udp' in globalvars.config['server']['protocols']:
        servers.append(
            socketserver.ThreadingUDPServer((ip, port), UDPRequestHandler)
        )
    if 'tcp' in globalvars.config['server']['protocols']:
        servers.append(
            socketserver.ThreadingTCPServer((ip, port), TCPRequestHandler),
        )

    for s in servers:
        # that thread will start one more thread for each request
        thread = threading.Thread(target=s.serve_forever)
        # exit the server thread when the main thread terminates
        thread.daemon = True
        thread.start()
        logger.error("%s server loop running in thread: %s" % (
            s.RequestHandlerClass.__name__[:3],
            thread.name
        ))

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for s in servers:
            s.shutdown()

if __name__ == '__main__':
    run()
