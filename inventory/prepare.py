#!/usr/bin/env python
# dynamic inventory for prepare.yml playbook
#   retrieves the ip address of the local kvm domain
# ex: ansible-playbook prepare.yml -i inventory/prepare.py
import os
import json
import yaml
import logging

import libvirt

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
ANSIBLE_PATH = os.path.dirname(BASE_PATH)
CRED_PATH = os.path.join(ANSIBLE_PATH, "group_vars", "all.yml")
GUNSEN_PATH = os.path.join(ANSIBLE_PATH, "group_vars", "gunsen.yml")

DOMAIN_NAME = "BASE-1"

def kvm_inventory():
    conn = libvirt.open("qemu:///system")
    domains = conn.listAllDomains()
    base_domain = [ dom for dom in domains if dom.name() == DOMAIN_NAME ]
    if not base_domain:
        logging.error("Domain {} not found.".format(DOMAIN_NAME))
        return

    # get ip address of kvm domain (vnet0)
    interfaces = base_domain[0].interfaceAddresses(0)
    try:
        host = interfaces["vnet0"]["addrs"][0]["addr"]
    except KeyError, e:
        logging.error("Missing key: {}".format(e))
        return

    if host.startswith("169.254"):
        logging.error("APIPA detected!")
        return

    # load gunsen settings specified in 'gunsen.yml'
    with open(GUNSEN_PATH, "rb") as fp:
        hostvars = yaml.load(fp.read(), Loader=yaml.Loader)

    # load login credentials specified in 'all.yml'
    with open(CRED_PATH, "rb") as fp:
        cred =  yaml.load(fp.read(), Loader=yaml.Loader)

    hostvars.update(cred)

    template = {
        "prepare": [ host ],
        "_meta": {
            "hostvars": { host: hostvars }
        }
    }
    print json.dumps(template)

kvm_inventory()
