#!/usr/bin/env python
# kvm_create_xml.py - populating base xmldesc of libvirt domains
import argparse
import os
import subprocess
import time
import xml.etree.ElementTree as ET

def cmd(c):
    if isinstance(c, str):
        c = c.split()
    p = subprocess.Popen(c)
    p.communicate()

def create_ovl(base_image_file, name="BASE", count=1):
    """ create storage overlays """
    qemu_cmd = "qemu-img create -f qcow2 -b {}".format(base_image_file)
    base_image_path = os.path.dirname(base_image_file)
    for i in xrange(count):
        new_name = "{}-{}.ovl".format(name, i+1)
        path = os.path.join(base_image_path, new_name)
        q = "{} {}".format(qemu_cmd, path)
        cmd(q)

def create_xml(base_template_file, name="BASE", count=1, mem="4096", cpu="2", disk=None):
    """ create xml descriptors for overlays"""
    base_template_path = os.path.dirname(base_template_file)
    xmldesc = ET.parse(base_template_file).getroot()
    templates = []

    for i in xrange(count):
        new_name = "{}-{}".format(name, i+1)
        filename = new_name + ".xmlovl"
        dom = xmldesc.copy()
        dom.find("./name").text = new_name
        dom.find("./memory").text = str(mem)
        dom.find("./currentMemory").text = str(mem)
        dom.find("./vcpu").text = str(cpu)

        # use disk value as an override, else point to generated overlay
        if disk:
            diskpath = disk
        else:
            diskpath = os.path.join(base_template_path, new_name + ".ovl")

        dom.find("./devices/disk/source").attrib["file"] = diskpath
        output_path = os.path.join(base_template_path, filename)
        with open(output_path, "wb") as f:
            f.write(ET.tostring(dom))
        templates.append(output_path)
    return templates

def create_vms(templates=[], is_temporary=False):
    """ create kvm domains based on templates"""
    virt_cmd = "virsh -c qemu:///system"

    for template in templates:
        domain = os.path.basename(template).strip(".xmlovl")
        # define vm
        if is_temporary:
            c = "{} create {}".format(virt_cmd, template)
            cmd(c)
        else:
            c = "{} define {}".format(virt_cmd, template)
            cmd(c)
            a = "{} autostart {}".format(virt_cmd, domain)
            cmd(a)
            s = "{} start {}".format(virt_cmd, domain)
            cmd(s)
        time.sleep(1)

def main(args):
    create_ovl(
        name = args.name,
        base_image_file = args.base_image,
        count = args.count
    )

    templates = create_xml(
        base_template_file = os.path.abspath(args.base_template),
        name = args.name,
        count = args.count,
        mem = args.mem,
        cpu = args.cpu
    )
    create_vms(templates = templates)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("base_image", help="Base QCOW2 Image File")
    parser.add_argument("base_template", help="Base XMLDesc Template File")
    parser.add_argument("-c", "--count", default=1, type=int)
    parser.add_argument("-n", "--name", default="BASE")
    parser.add_argument("--mem", default="4096")
    parser.add_argument("--cpu", default="2")
    args = parser.parse_args()

    main(args)
