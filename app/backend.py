"""Sekiro 1.06 PC offline consumable editor. No process-memory writes."""
from __future__ import annotations
import ctypes, hashlib, json, os, struct, tempfile, sys
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else ROOT
CATALOG = json.loads((DATA_ROOT / 'catalog_all.json').read_text(encoding='utf-8'))
SEN_LIMIT = 999_999_999  # 1.06 native Sen setter 0x14066da30 clamps to this value.
SEN = 0x344D0
EMBLEM_CAP = 0x3459A
GOURD_CAP = 0x34562
REGIONS = {'carry': (0x8F70C, 0x7000, 0x8F6FC, 0x8F700),
           'storage': (0x987A0, 0x9000, 0x98790, 0x98794)}
# Replenish only resources that already have a record in the selected save slot.
GROUPS = {
 '资源': [1000, 3700, 3704, 3708],
 '糖': [3400, 3410, 3420, 3430, 3440],
 '药与恢复': [3000, 3020, 3040, 3050, 3051, 3052, 3053, 3060, 3061,
              3070, 3071, 3080, 3081, 3200, 3210, 3211, 3220, 3230, 3250, 3290, 5600],
 '已拥有的葫芦与降灵': [3300, 3310, 3320, 3350, 3360, 3370, 3380, 3390],
 '其他消耗品': [3450, 3500, 3510, 3520, 3530, 3600, 3610, 3620, 3630, 3640, 3720, 3721]
}
TARGETS = {i for group in GROUPS.values() for i in group}
OWNED_ONLY = TARGETS.copy()
# PC 1.06 USER_DATA010 menu: each slot has a 0x218-byte summary.
# Display its stored calendar value without guessing a timezone or creation date.
SLOT_TIME_START = 0x2E0
SLOT_SUMMARY_STRIDE = 0x218

def u32(d, o): return struct.unpack_from('<I', d, o)[0]
def put32(d, o, v): struct.pack_into('<I', d, o, v)
def sha(d): return hashlib.sha256(d).hexdigest()

class SaveError(ValueError): pass

@dataclass(frozen=True)
class Entry:
    offset: int
    size: int
    name: str
    @property
    def payload(self): return self.offset + 16
    @property
    def length(self): return self.size - 16

class Save:
    def __init__(self, data: bytes, account: int | None = None):
        self.data = bytes(data)
        if len(data) < 512 or data[:4] != b'BND4' or u32(data,12) != 12 or u32(data,32) != 32:
            raise SaveError('不支持的存档容器：仅支持本机验证过的只狼 PC 1.06 BND4 格式。')
        self.entries=[]
        for i in range(12):
            h=64+32*i
            size=struct.unpack_from('<Q',data,h+8)[0]; off=u32(data,h+16); no=u32(data,h+20)
            if off < 0x300 or size < 16 or off+size>len(data) or no>=0x300:
                raise SaveError('存档条目边界异常。')
            end=no
            while end+1<0x300 and data[end:end+2]!=b'\0\0': end+=2
            name=data[no:end].decode('utf-16-le')
            if name!=f'USER_DATA{i:03d}':raise SaveError('存档条目名称异常。')
            if data[off:off+16] != hashlib.md5(data[off+16:off+size]).digest():
                raise SaveError(f'条目 {i} 校验失败；拒绝修改损坏或同步中的存档。')
            self.entries.append(Entry(off,size,name))
        spans=sorted((e.offset,e.offset+e.size) for e in self.entries)
        if any(a[1]>b[0] for a,b in zip(spans,spans[1:])):raise SaveError('存档条目重叠。')
        if any(e.length != 0x100000 for e in self.entries[:10]):raise SaveError('存档条目大小异常。')
        menu=self.entries[10]
        occupied=data[menu.payload+212:menu.payload+222]
        if len(occupied)!=10 or any(b not in (0,1) for b in occupied):raise SaveError('存档占用标记异常。')
        self.active=[i for i,b in enumerate(occupied) if b]
        for slot in self.active:
            p=self.slot(slot)
            sid=struct.unpack_from('<Q',p,0x33e54)[0]
            if not sid or (account is not None and sid!=account):raise SaveError('账号标识不匹配，拒绝修改。')
            if not 15 <= self.emblem_cap(slot) <=20 or not 1<=self.gourd_cap(slot)<=10:
                raise SaveError('容量字段不符合已验证的 1.06 格式。')
            for zone in REGIONS:self.records(slot,zone)
    def slot(self,slot):
        e=self.entries[slot]; return self.data[e.payload:e.payload+e.length]
    def recorded_time(self,slot):
        """Return the slot's recorded game-save time, not filesystem/creation time.

        This game calendar has millisecond precision. It is preserved verbatim
        during quantity edits. A missing/invalid field never uses file mtime.
        """
        if slot not in self.active:raise SaveError('不能读取已删除或无效存档的时间。')
        menu=self.slot(10)
        offset=SLOT_TIME_START+SLOT_SUMMARY_STRIDE*slot
        if offset+8>len(menu):return None
        ticks=struct.unpack_from('<Q',menu,offset)[0]
        if not ticks:return None
        try:recorded=datetime(1601,1,1)+timedelta(microseconds=ticks//10)
        except OverflowError:return None
        if not 2000<=recorded.year<=2099:return None
        return recorded
    def slot_label(self,slot):
        recorded=self.recorded_time(slot)
        text=recorded.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] if recorded else '时间未知'
        return f'存档 {slot+1} | {text}'
    def emblem_cap(self,slot):return struct.unpack_from('<H',self.slot(slot),EMBLEM_CAP)[0]
    def gourd_cap(self,slot):return self.slot(slot)[GOURD_CAP]
    def records(self,slot,zone):
        p=self.slot(slot);start,size,index,count=REGIONS[zone]; rows={};occupied=0
        for o in range(start,start+size,16):
            h,i,q,s=struct.unpack_from('<IIII',p,o)
            if not h:continue
            occupied+=1
            if i>>28==4:
                id=i&0x0fffffff
                if h != 0xb0000000|id:raise SaveError(f'{zone} 物品句柄异常。')
                if id in rows:raise SaveError(f'{zone} 有重复物品 {id}，需要人工确认。')
                rows[id]=(o,q,s)
        if occupied!=u32(p,count):raise SaveError(f'{zone} 数量计数不一致 ({occupied}/{u32(p,count)})。')
        if not 0<=u32(p,index)<=0xfff:raise SaveError('物品排序序号异常。')
        return rows
    def quantities(self,slot,id):
        return tuple(self.records(slot,z).get(id,(0,0,0))[1] for z in REGIONS)
    def caps(self,slot,id):
        r=CATALOG[str(id)];carry=r['carry_max']
        if id==1000:carry=self.emblem_cap(slot)
        if id==3000:carry=self.gourd_cap(slot)
        return carry,r['storage_max']
    def owned(self,slot,id):
        return any(id in self.records(slot,z) for z in REGIONS)
    def maximum_plan(self,slot):
        return {str(i):dict(zip(REGIONS,self.caps(slot,i))) for i in sorted(TARGETS)
                if i not in OWNED_ONLY or self.owned(slot,i)}
    def edit(self,slot,sen,items):
        if slot not in self.active:raise SaveError('拒绝修改空白或已删除的存档。')
        if not isinstance(sen,int) or isinstance(sen,bool) or not 0<=sen<=SEN_LIMIT:raise SaveError('钱币超出本机版本已验证的范围（0～999999999）。')
        p=bytearray(self.slot(slot));ranges=[(SEN,SEN+4)];changes=[]
        if u32(p,SEN)!=sen:changes.append({'resource':'钱币','before':u32(p,SEN),'after':sen})
        put32(p,SEN,sen)
        for key,quantities in items.items():
            id=int(key)
            if id not in TARGETS:raise SaveError(f'物品 {id} 不在安全白名单。')
            if id in OWNED_ONLY and not self.owned(slot,id):raise SaveError(f'不会生成尚未获得的物品 {id}。')
            if set(quantities)!=set(REGIONS):raise SaveError('必须分别填写随身和仓库数量。')
            for n,(zone,value) in enumerate(quantities.items()):
                cap=self.caps(slot,id)[list(REGIONS).index(zone)]
                if not isinstance(value,int) or isinstance(value,bool) or not 0<=value<=cap:
                    raise SaveError(f'{CATALOG[str(id)]["name"]} {zone} 的数量应为 0～{cap}。')
                start,size,index,count=REGIONS[zone]
                # Re-scan modified buffer so multiple insertions see each other.
                row=None
                for o in range(start,start+size,16):
                    if u32(p,o) and u32(p,o+4)==0x40000000|id:row=o;break
                before=u32(p,row+8) if row is not None else 0
                if row is None and value:
                    # Insertion is restricted to the known, tested initial region.
                    candidates=range(start,start+min(size,0x1000),16)
                    row=next((o for o in candidates if u32(p,o)==0 and u32(p,o+4) in (0,0xffffffff)),None)
                    if row is None:raise SaveError('已验证的物品区没有空位，拒绝扩大写入范围。')
                    idx=u32(p,index)+1
                    if idx>0xfff:raise SaveError('物品排序序号已耗尽。')
                    sort=(CATALOG[str(id)]['sort_id']<<12)|idx
                    if not 0<=sort<=0xffffffff:raise SaveError('物品排序参数异常。')
                    struct.pack_into('<IIII',p,row,0xb0000000|id,0x40000000|id,value,sort)
                    put32(p,index,idx);put32(p,count,u32(p,count)+1)
                    ranges += [(row,row+16),(index,index+4),(count,count+4)]
                elif row is not None:
                    put32(p,row+8,value);ranges.append((row+8,row+12))
                if before!=value:changes.append({'id':id,'name':CATALOG[str(id)]['name'],'zone':zone,'before':before,'after':value})
        # Whitelist byte-difference proof (quest flags/stat/other slots cannot change).
        allowed=bytearray(len(p))
        for a,b in ranges:allowed[a:b]=b'\1'*(b-a)
        if any(a!=b and not allowed[o] for o,(a,b) in enumerate(zip(self.slot(slot),p))):raise SaveError('出现白名单外的字节改动。')
        e=self.entries[slot];out=bytearray(self.data)
        out[e.offset:e.offset+16]=hashlib.md5(p).digest();out[e.payload:e.payload+e.length]=p
        parsed=Save(bytes(out))
        for i,entry in enumerate(self.entries):
            if i!=slot and out[entry.offset:entry.offset+entry.size]!=self.data[entry.offset:entry.offset+entry.size]:raise SaveError('非目标条目变化。')
        if out[:0x300]!=self.data[:0x300]:raise SaveError('容器头变化。')
        for key,q in items.items():
            if parsed.quantities(slot,int(key))!=tuple(q[z] for z in REGIONS):raise SaveError('写入后数量验证失败。')
        return bytes(out),changes

def game_running():
    if os.name!='nt':return False
    from ctypes import wintypes as W
    class P(ctypes.Structure):
        _fields_=[('size',W.DWORD),('usage',W.DWORD),('pid',W.DWORD),('heap',ctypes.c_size_t),
                  ('module',W.DWORD),('threads',W.DWORD),('parent',W.DWORD),('priority',W.LONG),('flags',W.DWORD),('exe',W.WCHAR*260)]
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];k.CreateToolhelp32Snapshot.restype=W.HANDLE
    k.Process32FirstW.argtypes=[W.HANDLE,ctypes.POINTER(P)];k.Process32NextW.argtypes=[W.HANDLE,ctypes.POINTER(P)];k.CloseHandle.argtypes=[W.HANDLE]
    h=k.CreateToolhelp32Snapshot(2,0)
    if h==ctypes.c_void_p(-1).value:raise OSError(ctypes.get_last_error(),'无法检查游戏进程')
    try:
        p=P();p.size=ctypes.sizeof(P);more=k.Process32FirstW(h,ctypes.byref(p))
        while more:
            if p.exe.lower()=='sekiro.exe':return True
            more=k.Process32NextW(h,ctypes.byref(p))
        return False
    finally:k.CloseHandle(h)

def atomic_write(path,data):
    fd,name=tempfile.mkstemp(prefix=path.name+'.staged-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        if Path(name).read_bytes()!=data:raise SaveError('临时文件回读失败。')
        os.replace(name,path)
    finally:
        if Path(name).exists():Path(name).unlink()

def apply(path,expected,slot,sen,items):
    """Replace the current game save, without retaining backups or history."""
    path=Path(path)
    if game_running():raise SaveError('请先退出只狼。工具不会修改运行中游戏的数据。')
    if path.name!='S0000.sl2' or not path.parent.name.isdigit():raise SaveError('请选择数字账号目录下的 S0000.sl2。')
    before=path.read_bytes()
    if sha(before)!=expected:raise SaveError('游戏数据已变化（可能是游戏或云同步），请关闭并重新打开程序。')
    account=int(path.parent.name);save=Save(before,account)
    out,changes=save.edit(slot,sen,items)
    if game_running() or path.read_bytes()!=before:raise SaveError('保存时游戏已启动或数据发生变化，已取消。')
    if out!=before:
        atomic_write(path,out)
        if path.read_bytes()!=out:raise SaveError('保存后回读不一致。请勿继续游戏，先检查磁盘和云同步状态。')
    return changes

def find_saves():
    base=Path(os.environ.get('APPDATA',''))/'Sekiro'
    return sorted(base.glob('*/S0000.sl2'),key=lambda p:p.stat().st_mtime,reverse=True)
