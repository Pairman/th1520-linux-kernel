#!/usr/bin/env python3
"""Execute the actual UART TX-IRQ and startup DMA blocks with mock state.

No hardware is touched. This checks dispatch/callback preservation, not UART
register semantics or real interrupt timing.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "drivers/tty/serial/8250/8250_port.c").read_text()


def block(marker):
    start = SOURCE.index(marker)
    end = SOURCE.index("{", start) + 1
    depth = 1
    while depth:
        depth += (SOURCE[end] == "{") - (SOURCE[end] == "}")
        end += 1
    return SOURCE[start:end]


irq = block("if ((status & UART_LSR_THRE) && (up->ier & UART_IER_THRI))")
startup = block("if (up->dma) {\n\t\tconst char *msg = NULL;")
c = r'''
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#define UART_LSR_THRE 1
#define UART_IER_THRI 1
#define dev_warn_ratelimited(...) do {} while (0)
struct dma { void *rxchan, *txchan; int tx_err, tx_running;
             int (*rx_dma)(void *), (*tx_dma)(void *); };
struct port { int console; void *dev; };
struct uart { struct dma *dma; struct port port; int ier; };
static int sent, stopped, request_error;
static void serial8250_tx_chars(struct uart *up) { sent++; }
static void __stop_tx(struct uart *up) { stopped++; }
static int uart_console(struct port *p) { return p->console; }
static int serial8250_request_dma(struct uart *up) { return request_error; }
static int callback(void *p) { return 0; }
static void tx_irq(struct uart *up) {
    int status = UART_LSR_THRE;
''' + irq + r'''
}
static void startup(struct uart *up) {
    struct port *port = &up->port;
''' + startup + r'''
}
int main(void) {
    int channel;
    for (int rx=0; rx<2; rx++) for (int tx=0; tx<2; tx++) {
        struct dma d = { .rxchan=rx?&channel:NULL, .txchan=tx?&channel:NULL,
                        .rx_dma=callback, .tx_dma=callback };
        struct uart up = { .dma=&d, .ier=UART_IER_THRI };
        startup(&up);
        assert(up.dma == ((rx || tx) ? &d : NULL));
        assert(d.rx_dma == callback && d.tx_dma == callback);
        sent=stopped=0; tx_irq(&up);
        assert(sent == !tx && stopped == !!tx);
        if (tx) {
            d.tx_err=1; sent=stopped=0; tx_irq(&up); assert(sent==1&&!stopped);
            d.tx_err=0; d.tx_running=1;
            sent=stopped=0; tx_irq(&up); assert(!sent&&!stopped);
        }
        /* Simulate close and reopen with both directions now available. */
        if (rx || tx) {
            d.rxchan=d.txchan=NULL;
            d.rxchan=d.txchan=&channel;
            startup(&up);
            assert(d.rx_dma == callback && d.tx_dma == callback);
        }
    }
    struct dma d={.rx_dma=callback,.tx_dma=callback};
    struct uart up={.dma=&d,.port={.console=1}};
    startup(&up); assert(!up.dma);
    up.dma=&d; up.port.console=0; request_error=-1;
    startup(&up); assert(!up.dma);
    puts("actual UART IRQ/startup blocks: PASS");
}
'''
with tempfile.TemporaryDirectory() as folder:
    source = Path(folder) / "test.c"
    binary = Path(folder) / "test"
    source.write_text(c)
    subprocess.run(["gcc", "-std=c11", "-Wall", "-Werror", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
