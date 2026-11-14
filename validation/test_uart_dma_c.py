#!/usr/bin/env python3
import re,sys,tempfile,subprocess, pathlib

def extract(s,name):
 m=re.search(r'\b(?:int|void)\s+'+name+r'\s*\(',s); start=m.start(); brace=s.index('{',m.end()); d=0
 for i in range(brace,len(s)):
  if s[i]=='{': d+=1
  elif s[i]=='}':
   d-=1
   if d==0:return s[start:i+1]
 raise ValueError(name)

HDR=r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef unsigned long dma_addr_t; typedef unsigned long phys_addr_t; typedef unsigned long size_t;
#define PAGE_SIZE 4096
#define GFP_KERNEL 0
#define DMA_SLAVE 1
#define DMA_DEV_TO_MEM 2
#define DMA_MEM_TO_DEV 3
#define DMA_SLAVE_BUSWIDTH_1_BYTE 1
#define DMA_RESIDUE_GRANULARITY_DESCRIPTOR 9
#define UART_RX 0
#define UART_TX 0
#define UART_XMIT_SIZE 64
#define DMA_TO_DEVICE 4
#define dev_dbg_once(...) do{}while(0)
struct dev { struct dev *dev; int id; }; struct xmit { char *buf; }; struct state { struct xmit xmit; }; struct uart_port { struct dev *dev; unsigned long mapbase; struct state *state; };
struct dma_slave_config { int direction,src_addr_width,dst_addr_width; unsigned long src_addr,dst_addr; };
struct chan { struct dev *device; int released; }; struct dma_slave_caps { int cmd_pause,cmd_terminate,residue_granularity; };
struct uart_8250_dma { struct chan *rxchan,*txchan; void *rx_buf; size_t rx_size; struct dma_slave_config rxconf,txconf; dma_addr_t rx_addr,tx_addr; int rx_dma_addr,tx_dma_addr; void *fn,*rx_param,*tx_param; int rx_running,tx_running; };
struct uart_8250_port { struct uart_port port; struct uart_8250_dma *dma; };
typedef int dma_cap_mask_t; static int have_rx,have_tx,rx_caps=1,tx_caps=1,rx_alloc=1,tx_map=1; static int released, bad, allocs, frees, maps, unmaps;
static struct chan RC={0},TC={0};
static void *dma_request_slave_channel_compat(int m,void*f,void*p,struct dev*d,const char*n){if(n[0]=='r')return have_rx?&RC:NULL;return have_tx?&TC:NULL;}
static int dma_get_slave_caps(struct chan*c,struct dma_slave_caps*x){*x=(struct dma_slave_caps){1,1,0};int cap=c==&RC?rx_caps:tx_caps;if(cap==2)x->cmd_terminate=0;return cap==0?-1:0;}
static int dmaengine_slave_config(struct chan*c,void*x){return 0;}
static void *dma_alloc_coherent(struct dev*d,size_t n,dma_addr_t*a,int g){if(!rx_alloc)return NULL;*a=10;allocs++; return malloc(n);}
static dma_addr_t dma_map_single(struct dev*d,void*b,size_t n,int dir){if(tx_map){maps++;return 20;}return 0;}
static int dma_mapping_error(struct dev*d,dma_addr_t a){return !a;}
static void dma_unmap_single(struct dev*d,dma_addr_t a,size_t n,int dir){if(a)unmaps++;}
static void dmaengine_terminate_sync(struct chan*c){}
static void dma_free_coherent(struct dev*d,size_t n,void*b,dma_addr_t a){if(!b)bad=1;frees++;free(b);}
static void dma_release_channel(struct chan*c){if(!c||c->released){bad=1;return;}c->released=1;released++;}
#define dma_cap_zero(x) do{}while(0)
#define dma_cap_set(x,y) do{}while(0)
'''

def run(tree, expect_fail):
 src=pathlib.Path(tree+'/drivers/tty/serial/8250/8250_dma.c').read_text(); req=extract(src,'serial8250_request_dma'); rel=extract(src,'serial8250_release_dma')
 tests=r'''
int main(){ char b[64]; struct state st={{b}}; struct dev dv={&dv,1}; struct uart_8250_port p={{&dv,1,&st},0}; struct uart_8250_dma d={0}; p.dma=&d;
for(int rx=0;rx<2;rx++)for(int tx=0;tx<2;tx++)for(int rc=0;rc<3;rc++)for(int tc=0;tc<3;tc++)for(int ra=0;ra<2;ra++)for(int tm=0;tm<2;tm++){
have_rx=rx;have_tx=tx;rx_caps=rc;tx_caps=tc;rx_alloc=ra;tx_map=tm;RC.released=TC.released=0; RC.device=TC.device=&dv; released=bad=allocs=frees=maps=unmaps=0;d=(struct uart_8250_dma){0};int r=serial8250_request_dma(&p); if(bad){fprintf(stderr,"bad cleanup rx%d tx%d rc%d tc%d ra%d tm%d\n",rx,tx,rc,tc,ra,tm);return 2;} if(r==0){ serial8250_release_dma(&p); if(d.rxchan||d.txchan||allocs!=frees||maps!=unmaps){fprintf(stderr,"leak case rx%d tx%d\n",rx,tx);return 3;} } else if(allocs!=frees||maps!=unmaps||(rx&&!RC.released)||(tx&&d.txchan&&!TC.released)){fprintf(stderr,"failure-path resource leak rx%d tx%d rc%d tc%d ra%d tm%d\n",rx,tx,rc,tc,ra,tm);return 4;} }
return 0;}
'''
 with tempfile.TemporaryDirectory() as td:
  c=pathlib.Path(td)/'t.c'; exe=pathlib.Path(td)/'t'; c.write_text(HDR+'\n'+req+'\n'+rel+'\n'+tests)
  cp=subprocess.run(['gcc','-std=gnu11','-Wno-unused-function','-o',str(exe),str(c)],capture_output=True,text=True)
  if cp.returncode: print(cp.stderr);return False
  rp=subprocess.run([str(exe)],capture_output=True,text=True)
  print('C harness',tree, 'exit',rp.returncode, rp.stderr.strip())
  return (rp.returncode!=0) if expect_fail else (rp.returncode==0)

def main():
 root = pathlib.Path(__file__).resolve().parents[1]
 if len(sys.argv)==3:
  a=run(sys.argv[1],True); b=run(sys.argv[2],False)
 elif len(sys.argv)==1:
  with tempfile.TemporaryDirectory() as folder:
   dest=pathlib.Path(folder)/'drivers/tty/serial/8250'; dest.mkdir(parents=True)
   (dest/'8250_dma.c').write_bytes(subprocess.check_output(['git','show','4a0d16a52295:drivers/tty/serial/8250/8250_dma.c'],cwd=root))
   a=run(folder,True); b=run(str(root),False)
 else: raise SystemExit('usage: test_uart_dma_c.py [ORIGINAL FIXED]')
 if not (a and b): raise SystemExit(1)
 print('PASS: extracted actual serial8250_request_dma executes: original fails expected, fixed passes all combinations')
main()
