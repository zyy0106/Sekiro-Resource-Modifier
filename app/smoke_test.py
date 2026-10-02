"""Explicit portable-build smoke test; uses synthetic data, never real saves."""
import hashlib
import json
import struct
import tempfile
from datetime import datetime
from pathlib import Path
import backend as b


def fixture():
    account=76561198000000000
    sizes=[0x100010]*10+[0x2010,0x110]
    data=bytearray(0x300+sum(sizes))
    data[:4]=b'BND4'
    b.put32(data,12,12)
    b.put32(data,32,32)
    offset=0x300
    name_offset=0x1c0
    for i,size in enumerate(sizes):
        header=64+32*i
        struct.pack_into('<Q',data,header+8,size)
        b.put32(data,header+16,offset)
        b.put32(data,header+20,name_offset)
        name=(f'USER_DATA{i:03d}'+chr(0)).encode('utf-16-le')
        data[name_offset:name_offset+len(name)]=name
        name_offset+=len(name)
        if i==0:
            payload=bytearray(0x100000)
            struct.pack_into('<Q',payload,0x33e54,account)
            struct.pack_into('<H',payload,b.EMBLEM_CAP,17)
            payload[b.GOURD_CAP]=8
            for zone,(start,_,index,count) in b.REGIONS.items():
                struct.pack_into('<IIII',payload,start,0xb0000000|3440,0x40000000|3440,1,(b.CATALOG['3440']['sort_id']<<12)|1)
                b.put32(payload,index,1)
                b.put32(payload,count,1)
            data[offset+16:offset+size]=payload
        if i==10:
            data[offset+16+212]=1
            delta=datetime(2026,10,2,12,34,56,789000)-datetime(1601,1,1)
            ticks=(delta.days*86400+delta.seconds)*10000000+delta.microseconds*10
            struct.pack_into('<Q',data,offset+16+b.SLOT_TIME_START,ticks)
        data[offset:offset+16]=hashlib.md5(data[offset+16:offset+size]).digest()
        offset+=size
    return account,bytes(data)


def run(report_path):
    """Return process exit status and write a report only when explicitly requested."""
    report={'passed':False,'synthetic_data_only':True}
    try:
        import gui
        with tempfile.TemporaryDirectory(prefix='sekiro_modifier_smoke_') as folder:
            account,data=fixture()
            path=Path(folder)/str(account)/'S0000.sl2'
            path.parent.mkdir()
            path.write_bytes(data)
            old_find,old_running=b.find_saves,b.game_running
            old_info,old_error=gui.messagebox.showinfo,gui.messagebox.showerror
            b.find_saves=lambda:[path]
            b.game_running=lambda:False
            gui.messagebox.showinfo=lambda *a,**k:None
            def unexpected_error(*args,**kwargs):raise AssertionError(str(args))
            gui.messagebox.showerror=unexpected_error
            app=None
            try:
                app=gui.App()
                app.withdraw()
                app.update()
                assert app.slotvar.get()=='存档 1 | 2026-10-02 12:34:56.789'
                assert len(app.tree.get_children())==50
                app.tree.selection_set('3440')
                app.update()
                app.carry.set('3')
                app.store.set('9999')
                app.sen.set('12345')
                app.apply()
                saved=b.Save(path.read_bytes(),account)
                assert saved.quantities(0,3440)==(3,9999)
                assert b.u32(saved.slot(0),b.SEN)==12345
                assert saved.recorded_time(0)==b.Save(data).recorded_time(0)
                assert list(path.parent.iterdir())==[path]
                report.update(passed=True,tk_loaded=True,catalog_loaded=True,save_verified=True,no_history=True)
            finally:
                if app is not None:app.destroy()
                b.find_saves,b.game_running=old_find,old_running
                gui.messagebox.showinfo,gui.messagebox.showerror=old_info,old_error
    except Exception as exc:report['error']=str(exc)
    Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
