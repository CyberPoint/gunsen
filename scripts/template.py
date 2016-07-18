#!/usr/bin/env python
# sanitize-xmldesc.py - takes an xmldesc dump and creates a template
import os
import xml.etree.ElementTree as ET

import libvirt

connection = libvirt.open("qemu:///system")

def generate_template(filename, content):
    if not os.path.exists(filename):
        print "[+] {} created.".format(filename)
        with open(filename, "wb") as fp:
            fp.write(content)
    else:
        print "[!] {} already exists.".format(filename)

for domain in connection.listAllDomains():
    dom = ET.fromstring(domain.XMLDesc())
    filename = "domain-{}.xml".format(domain.name())

    dom.find("./name").text = "__NAME__"
    dom.find("./memory").attrib["unit"] = "MB"
    dom.find("./memory").text = "__MEMORY__"
    dom.find("./currentMemory").attrib["unit"] = "MB"
    dom.find("./currentMemory").text = "__MEMORY__"
    dom.find("./vcpu").text = "__VCPU__"
    dom.find("./devices/disk/source").attrib["file"] = "__DISK__"

    interface = dom.find("./devices/interface")
    mac = interface.find("./mac")
    interface.remove(mac)
    uid = dom.find("./uuid")
    dom.remove(uid)
    sec = dom.find("./seclabel")
    dom.remove(sec)

    generate_template(filename, ET.tostring(dom))
