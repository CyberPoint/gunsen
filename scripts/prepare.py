#!/usr/bin/env python
# prepare.py - kicks off local kvm domain deployment for image prep
import argparse
import os
import shutil
import subprocess
import datetime

import libvirt
import kvm_cleanup
import kvm_create

BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROLE_PATH = os.path.join(BASE_PATH, "roles")
DEPLOY_PATH = os.path.join(ROLE_PATH, "do.deploy", "files")
PREPARE_PATH = os.path.join(ROLE_PATH, "do.prepare", "files")

PREP_IMAGE_NAME = "haka-7-x86.qcow2"
PREP_TEMPLATE_NAME = "haka-7-x86.xml"

def cleanup():
    conn = libvirt.open("qemu:///system")
    kvm_cleanup.destroy_undefine_domains(conn, "BASE-1")
    kvm_cleanup.delete_overlay_templates(PREPARE_PATH)

def compress():
    com_src = os.path.join(PREPARE_PATH, PREP_IMAGE_NAME)
    com_dst = os.path.join(PREPARE_PATH, PREP_IMAGE_NAME + ".old")
    try:
        print "Compressing image ..."
        shutil.move(com_src, com_dst)
        compress_cmd = "qemu-img convert -c -O qcow2 {} {}".format(com_dst, com_src)
        subprocess.check_output(compress_cmd.split())
    finally:
        if os.path.exists(com_dst):
            os.remove(com_dst)

def export():
    name, ext = PREP_IMAGE_NAME.split(".")
    image_name = "{}.{}.qcow2".format(name, datetime.datetime.now().strftime("%Y%m%d"))
    exp_src = os.path.join(PREPARE_PATH, PREP_IMAGE_NAME)
    exp_dst = os.path.join(DEPLOY_PATH, image_name)
    if os.path.exists(exp_src):
        shutil.move(exp_src, exp_dst)
        print "Exported to: {}".format(exp_dst)
        template = os.path.join(PREPARE_PATH, PREP_IMAGE_NAME)
        if os.path.exists(template):
            os.remove(template)
    else:
        print "Nothing to export."

def main(args):
    if args.compress:
        args.export = True
        compress()

    if args.export:
        export()
        cleanup()
        return

    qcow_images = [ x for x in os.listdir(DEPLOY_PATH) if x.endswith(".qcow2") ]
    qcow_images.sort()

    # copy latest image from deploy to prepare
    img_src = os.path.join(DEPLOY_PATH, qcow_images[-1])
    img_dst = os.path.join(PREPARE_PATH, PREP_IMAGE_NAME)
    print "[*] Copying qcow2 image"
    print "SRC:", img_src
    print "DST:", img_dst
    shutil.copy(img_src, img_dst)

    # copy template from deploy to prepare
    tmp_src = os.path.join(DEPLOY_PATH, PREP_TEMPLATE_NAME)
    tmp_dst = os.path.join(PREPARE_PATH, PREP_TEMPLATE_NAME)
    print "[*] Copying xml template"
    print "SRC:", tmp_src
    print "DST:", tmp_dst
    shutil.copy(tmp_src, tmp_dst)

    diskpath = os.path.join(PREPARE_PATH, PREP_IMAGE_NAME)
    template = kvm_create.create_xml(tmp_dst, disk=diskpath)
    kvm_create.create_vms(template, is_temporary=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compress", action="store_true")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()

    main(args)
