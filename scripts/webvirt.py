#!/usr/bin/env python
# webvirt.py - flask server to allow nodes to interact directly
#   with kvm host for snapshot management and information retrieval
import argparse
import json
import os
import re

import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify
import libvirt

class KVM(object):
    def __init__(self):
        self.conn = libvirt.open("qemu:///system")
        self.inventory = self.get_inventory()

        try:
            basepath = os.path.dirname(os.path.abspath(__file__))
            filename = os.path.join(basepath, "kvm.name")
            with open(filename, "rb") as fp:
                self.name = fp.read().strip()
        except IOError, e:
            self.name = "kvm"
            logging.error("Unable to retrieve kvm name:\n{}".format(e))

    def __del__(self):
        self.conn.close()

    def node_reboot(self, domain):
        domains = [ dom.name() for dom in self.domains ]
        if domain not in domains:
            return

        try:
            domain = self.conn.lookupByName(domain)
            domain.reboot()
            return True
        except libvirt.libvirtError, e:
            logging.error("{} - Failed to reboot:\n{}".format(domain, e))

    def node_snapshot_create(self, domain):
        domains = [ dom.name() for dom in self.domains ]
        if domain not in domains:
            return

        xml_head = """<domainsnapshot> <name>snapshot</name>
        <state>running</state> <memory snapshot='internal'/>
        <disks><disk name='hda' snapshot='internal'/></disks>"""
        xml_tail = "</domainsnapshot>"
        try:
            domain = self.conn.lookupByName(domain)
            self.node_snapshot_clear(domain)
            xml_desc = xml_head + domain.XMLDesc() + xml_tail
            domain.snapshotCreateXML(xml_desc)
            return True
        except libvirt.libvirtError, e:
            logging.error("{} - Failed to create snapshot:\n{}".format(domain, e))

    def node_snapshot_revert(self, domain):
        domains = [ dom.name() for dom in self.domains ]
        if domain not in domains:
            return

        try:
            domain = self.conn.lookupByName(domain)
            self.node_snapshot_clear(domain)
            snap = domain.snapshotCurrent()
            if domain.revertToSnapshot(snap) == 0:
                return True
        except libvirt.libvirtError, e:
            logging.error("{} - Failed to revert snapshot:\n{}".format(domain, e))

    def node_snapshot_clear(self, domain):
        try:
            [ snapshot.delete() for snapshot in domain.listAllSnapshots() ]
        except libvirt.libvirtError, e:
            logging.error("Failed to clear snapshot: {}".format(e))

    def find_domain(self, **kwargs):
        inv = self.inventory
        if kwargs.has_key("mac"):
            mac = re.sub(":|-", "", kwargs["mac"]).lower()
            inv = [ i for i in inv if i["mac"] == mac ]
        elif kwargs.has_key("ip"):
            inv = [ i for i in inv if i["ip"] == kwargs["ip"] ]
        else:
            inv = None
        return inv

    @property
    def domains(self):
        return self.conn.listAllDomains()

    def get_inventory(self):
        inventory = []
        for domain in self.domains:
            net_info = domain.interfaceAddresses(0)
            for _, info in net_info.iteritems():
                mac = info["hwaddr"]
                ip = info["addrs"][0]["addr"]
                name = domain.name()

                info = {
                    "name": name,
                    "ip": ip,
                    "mac": re.sub(":|-", "", mac)
                }
                inventory.append(info)
        return inventory

    @property
    def version(self):
        return { "name": self.name }


webvirt = Flask(__name__)
kvm = KVM()

@webvirt.route("/")
def index():
    return jsonify(kvm.version)

@webvirt.route("/info/mac/<addr>")
def info_dom_name_by_mac(addr):
    """ returns domain name based on mac address """
    addr = re.sub(":|-", "", addr)
    dom = kvm.find_domain(mac=addr)
    if dom:
        name = "{}:{}".format(kvm.name, dom[0]["name"])
        return jsonify(name)
    else:
        return jsonify(None)

@webvirt.route("/info/ip/<addr>")
def info_dom_name_by_ip(addr):
    """ returns domain name based on ip address """
    dom = kvm.find_domain(ip=addr)
    if dom:
        name = "{}:{}".format(kvm.name, dom[0]["name"])
        return jsonify(name)
    else:
        return jsonify(None)

@webvirt.route("/node/<name>/snapshot/create")
def node_snapshot_create(name):
    """ create snapshot of node """
    return jsonify(kvm.node_snapshot_create(name))

@webvirt.route("/node/<name>/snapshot/revert")
def node_snapshot_revert(name):
    """ revert snapshot of node """
    return jsonify(kvm.node_snapshot_revert(name))

@webvirt.route("/node/<name>/reboot")
def node_reboot(name):
    """ reboot nodes """
    return jsonify(kvm.reboot(name))

def main(args):
    handler = RotatingFileHandler("webvirt.log", maxBytes=1000000)
    handler.setLevel(logging.INFO)
    webvirt.logger.addHandler(handler)
    webvirt.run(host=args.ip, port=args.port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", default=8080, type=int)
    parser.add_argument("-i", "--ip", default="192.168.122.1")
    args = parser.parse_args()

    main(args)
