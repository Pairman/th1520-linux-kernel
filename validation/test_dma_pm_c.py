#!/usr/bin/env python3
"""Small C mock checks for the TH1520 DMA PM/link fix.

This is deliberately source-backed: the script reads the patched functions and
refuses to run if their key operations change.  The C harness then exercises the
same branch order and error unwinding without touching hardware.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).parents[1]
DMA = (ROOT / "drivers/dma/dw-axi-dmac/dw-axi-dmac-platform.c").read_text()
I2C = (ROOT / "drivers/i2c/busses/i2c-designware-platdrv.c").read_text()

for text, required in ((DMA, (
    "clk_disable_unprepare(chip->cfgr_clk)",
    "SET_SYSTEM_SLEEP_PM_OPS(axi_dma_system_suspend, axi_dma_system_resume)",
    "SET_LATE_SYSTEM_SLEEP_PM_OPS(axi_dma_suspend_late, axi_dma_resume_early)",
    '"xuantie,th1520-axi-dma"',
)), (I2C, (
    "dw_i2c_link_dma_supplier",
    "of_parse_phandle_with_args",
    "DL_FLAG_AUTOREMOVE_CONSUMER",
    "return -EPROBE_DEFER",
))):
    missing = [x for x in required if x not in text]
    if missing:
        raise SystemExit("patched source is missing: " + ", ".join(missing))

def extract(source, name):
    import re
    m = re.search(r"static\s+(?:int|bool)\s+(?:__maybe_unused\s+)?" + name + r"\s*\([^)]*\)\s*\{", source)
    if not m:
        raise SystemExit("cannot extract " + name)
    depth = 1; end = m.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[m.start():end]

functions = "\n".join(extract(DMA, n) for n in (
    "axi_dma_resume", "axi_dma_uses_late_suspend", "axi_dma_system_suspend",
    "axi_dma_system_resume", "axi_dma_suspend_late", "axi_dma_resume_early"))
functions += "\n" + extract(I2C, "dw_i2c_link_dma_supplier")
c = r'''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#define __maybe_unused
#define EPROBE_DEFER 517
#define EINVAL 22
#define DL_FLAG_AUTOREMOVE_CONSUMER 4
struct device_node { int th; };
struct of_phandle_args { struct device_node *np; };
struct device { struct device_node *of_node; int mode, bound; };
struct platform_device { struct device dev; } supplier;
struct device_link { int unused; } link_obj;
struct clock { int fail, refs; };
struct axi_dma_chip { struct clock *cfgr_clk, *core_clk; };
static int en, irq, fs, fr, force_error, node_refs, dev_refs, exists=1, add_fail, locks, tx_index=1, parse_error, parse_calls;
static struct device_node node={1};
static int clk_prepare_enable(struct clock *c){if(c->fail)return -5; c->refs++; return 0;}
static void clk_disable_unprepare(struct clock *c){c->refs--;}
static void axi_dma_enable(struct axi_dma_chip *c){en++;}
static void axi_dma_irq_enable(struct axi_dma_chip *c){irq++;}
static bool of_device_is_compatible(struct device_node *n,const char *s){return n && n->th;}
static int pm_runtime_force_suspend(struct device *d){fs++;return force_error;}
static int pm_runtime_force_resume(struct device *d){fr++;return force_error;}
static int device_property_read_string(struct device *d,const char *p,const char **v){if(!d->mode)return -1;*v=d->mode==1?"dma":"pio";return 0;}
static int of_property_match_string(struct device_node *n,const char *p,const char *v){assert(!strcmp(p,"dma-names")&&!strcmp(v,"tx"));return tx_index;}
static int of_parse_phandle_with_args(struct device_node *n,const char *p,const char *cells,int i,struct of_phandle_args *args){assert(i==tx_index&&!strcmp(p,"dmas")&&!strcmp(cells,"#dma-cells"));parse_calls++;if(parse_error)return parse_error;node_refs++;args->np=&node;return 0;}
static void of_node_put(struct device_node *n){node_refs--;}
static struct platform_device *of_find_device_by_node(struct device_node *n){if(!exists)return 0;dev_refs++;return &supplier;}
static void device_lock(struct device *d){assert(!locks);locks++;}
static void device_unlock(struct device *d){locks--;}
static bool device_is_bound(struct device *d){return d->bound;}
static void put_device(struct device *d){dev_refs--;}
static struct device *expected_consumer;
static struct device_link *device_link_add(struct device *c,struct device *s,int f){assert(c==expected_consumer&&s==&supplier.dev&&f==DL_FLAG_AUTOREMOVE_CONSUMER);return add_fail?0:&link_obj;}
''' + functions + r'''
int main(void){
 struct clock a={0},b={0};struct axi_dma_chip chip={&a,&b};
 a.fail=1;assert(axi_dma_resume(&chip)==-5&&!a.refs&&!b.refs&&!en);
 a.fail=0;b.fail=1;assert(axi_dma_resume(&chip)==-5&&!a.refs&&!b.refs&&!en);
 b.fail=0;assert(!axi_dma_resume(&chip)&&a.refs==1&&b.refs==1&&en==1&&irq==1);
 struct device_node dn={0};struct device d={&dn,1,0};expected_consumer=&d;
 for(int th=0;th<2;th++){dn.th=th;fs=fr=0;force_error=-7;
 assert(axi_dma_system_suspend(&d)==(th?0:-7));assert(axi_dma_system_resume(&d)==(th?0:-7));
 assert(axi_dma_suspend_late(&d)==(th?-7:0));assert(axi_dma_resume_early(&d)==(th?-7:0));assert(fs==1&&fr==1);}
 d.mode=0;assert(!dw_i2c_link_dma_supplier(&d));d.mode=2;assert(!dw_i2c_link_dma_supplier(&d));
 d.mode=1;tx_index=-1;assert(!dw_i2c_link_dma_supplier(&d)&&!parse_calls&&!node_refs&&!dev_refs&&!locks);tx_index=1;
 parse_error=-22;assert(dw_i2c_link_dma_supplier(&d)==-22&&!node_refs&&!dev_refs&&!locks);parse_error=0;
 node.th=0;assert(!dw_i2c_link_dma_supplier(&d));node.th=1;
 exists=0;assert(dw_i2c_link_dma_supplier(&d)==-517&&!node_refs&&!dev_refs&&!locks);exists=1;
 supplier.dev.bound=0;assert(dw_i2c_link_dma_supplier(&d)==-517&&!node_refs&&!dev_refs&&!locks);
 supplier.dev.bound=1;add_fail=1;assert(dw_i2c_link_dma_supplier(&d)==-22&&!node_refs&&!dev_refs&&!locks);
 add_fail=0;assert(!dw_i2c_link_dma_supplier(&d));assert(!node_refs&&!dev_refs&&!locks);
 puts("actual DMA PM/link C functions: PASS");return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
    src = Path(d) / "test.c"; exe = Path(d) / "test"
    src.write_text(c)
    subprocess.run(["gcc", "-std=c11", "-Wall", "-Werror", str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
