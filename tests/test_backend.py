import sys,unittest,tempfile,struct,hashlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import backend as b
ACCOUNT=76561198000000000

def make_fixture():
 # Entirely synthetic save: no backup or real user data needed for testing.
 sizes=[0x100010]*10+[0x1010,0x110]
 data=bytearray(0x300+sum(sizes))
 data[:4]=b'BND4';b.put32(data,12,12);b.put32(data,32,32)
 offset=0x300;name_offset=0x1c0
 for i,size in enumerate(sizes):
  h=64+32*i;struct.pack_into('<Q',data,h+8,size);b.put32(data,h+16,offset);b.put32(data,h+20,name_offset)
  name=(f'USER_DATA{i:03d}'+chr(0)).encode('utf-16-le');data[name_offset:name_offset+len(name)]=name;name_offset+=len(name)
  if i in (0,1):
   p=bytearray(0x100000);struct.pack_into('<Q',p,0x33e54,ACCOUNT);struct.pack_into('<H',p,b.EMBLEM_CAP,17);p[b.GOURD_CAP]=8
   for zone,(start,length,index,count) in b.REGIONS.items():
    ids=sorted((b.TARGETS-{3050,3052,3053,3060,3061,3071,3081,3300,3320,3350,3360,3370,3380,3390,3721})-({3000} if zone=='storage' else set()))
    for n,id in enumerate(ids,1):
     sort=(b.CATALOG[str(id)]['sort_id']<<12)|n
     cap=17 if id==1000 and zone=='carry' else (8 if id==3000 and zone=='carry' else b.CATALOG[str(id)]['carry_max' if zone=='carry' else 'storage_max'])
     struct.pack_into('<IIII',p,start+(n-1)*16,0xb0000000|id,0x40000000|id,min(1,cap),sort)
    b.put32(p,index,len(ids));b.put32(p,count,len(ids))
   data[offset+16:offset+size]=p
  if i==10:
   data[offset+16+212]=1
   from datetime import datetime
   delta=datetime(2026,10,2,21,11,59,344000)-datetime(1601,1,1)
   ticks=(delta.days*86400+delta.seconds)*10000000+delta.microseconds*10
   struct.pack_into('<Q',data,offset+16+b.SLOT_TIME_START,ticks)
  data[offset:offset+16]=hashlib.md5(data[offset+16:offset+size]).digest();offset+=size
 return bytes(data)

class SaveTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.original=make_fixture();cls.save=b.Save(cls.original,ACCOUNT)
 def test_active_menu_not_residual_slot(self):self.assertEqual(self.save.active,[0])
 def test_recorded_time_and_precision(self):
  from datetime import datetime
  self.assertEqual(self.save.recorded_time(0),datetime(2026,10,2,21,11,59,344000))
  self.assertEqual(self.save.slot_label(0),'存档 1 | 2026-10-02 21:11:59.344')
 def test_deleted_slot_time_refused(self):
  with self.assertRaises(b.SaveError):self.save.recorded_time(1)
 def test_unknown_time_does_not_use_filesystem_time(self):
  data=bytearray(self.original);e=self.save.entries[10]
  struct.pack_into('<Q',data,e.payload+b.SLOT_TIME_START,0)
  data[e.offset:e.offset+16]=hashlib.md5(data[e.payload:e.payload+e.length]).digest()
  s=b.Save(data);self.assertIsNone(s.recorded_time(0));self.assertEqual(s.slot_label(0),'存档 1 | 时间未知')
 def test_resource_edit_preserves_recorded_time(self):
  out,_=self.save.edit(0,999,self.save.maximum_plan(0))
  self.assertEqual(b.Save(out).recorded_time(0),self.save.recorded_time(0))
 def test_missing_ordinary_consumable_not_generated(self):
  data=bytearray(self.original);entry=self.save.entries[0];p=bytearray(self.save.slot(0))
  for zone in b.REGIONS:
   o=self.save.records(0,zone)[3440][0];p[o:o+16]=bytes(16)
   b.put32(p,b.REGIONS[zone][3],b.u32(p,b.REGIONS[zone][3])-1)
  data[entry.payload:entry.payload+entry.length]=p;data[entry.offset:entry.offset+16]=hashlib.md5(p).digest()
  s=b.Save(data)
  self.assertNotIn('3440',s.maximum_plan(0))
  with self.assertRaises(b.SaveError):s.edit(0,999,{'3440':{'carry':3,'storage':9999}})
 def test_caps(self):
  self.assertEqual(self.save.caps(0,1000),(17,999));self.assertEqual(self.save.caps(0,3000),(8,0));self.assertEqual(self.save.caps(0,3440),(3,9999))
 def test_roundtrip_unchanged(self):
  s=self.save;plan={str(i):dict(zip(b.REGIONS,s.quantities(0,i))) for i in b.TARGETS if i not in b.OWNED_ONLY or s.owned(0,i)}
  out,c=s.edit(0,b.u32(s.slot(0),b.SEN),plan);self.assertEqual(out,self.original);self.assertEqual(c,[])
 def test_all_max_readback(self):
  s=self.save;out,c=s.edit(0,b.SEN_LIMIT,s.maximum_plan(0));n=b.Save(out)
  for key,q in s.maximum_plan(0).items():self.assertEqual(n.quantities(0,int(key)),tuple(q[z] for z in b.REGIONS))
  self.assertEqual(b.u32(n.slot(0),b.SEN),b.SEN_LIMIT);self.assertGreater(len(c),40)
 def test_non_target_entries_identical(self):
  s=self.save;out,_=s.edit(0,b.SEN_LIMIT,s.maximum_plan(0))
  self.assertEqual(out[:0x300],self.original[:0x300])
  for e in s.entries[1:]:self.assertEqual(out[e.offset:e.offset+e.size],self.original[e.offset:e.offset+e.size])
 def test_upgrade_and_quest_regions_unchanged(self):
  s=self.save;out,_=s.edit(0,b.SEN_LIMIT,s.maximum_plan(0));p=b.Save(out).slot(0);old=s.slot(0)
  self.assertEqual(p[:b.SEN],old[:b.SEN]);self.assertEqual(p[b.SEN+4:0x8f6fc],old[b.SEN+4:0x8f6fc]);self.assertEqual(p[0x9670c:0x98790],old[0x9670c:0x98790]);self.assertEqual(p[0xa1958:],old[0xa1958:])
 def test_insert_fields_and_counters(self):
  # An already obtained item may have a record in only one inventory region.
  data=bytearray(self.original);entry=self.save.entries[0];p=bytearray(self.save.slot(0))
  o=self.save.records(0,'carry')[3440][0];p[o:o+16]=bytes(16)
  b.put32(p,b.REGIONS['carry'][3],b.u32(p,b.REGIONS['carry'][3])-1)
  data[entry.payload:entry.payload+entry.length]=p;data[entry.offset:entry.offset+16]=hashlib.md5(p).digest()
  s=b.Save(data);out,_=s.edit(0,4,{'3440':{'carry':3,'storage':9999}});n=b.Save(out)
  start,size,index,count=b.REGIONS['carry'];o,q,sort=n.records(0,'carry')[3440]
  self.assertEqual(b.u32(n.slot(0),index),b.u32(s.slot(0),index)+1)
  self.assertEqual(b.u32(n.slot(0),count),b.u32(s.slot(0),count)+1)
  self.assertEqual(sort>>12,b.CATALOG['3440']['sort_id'])
  self.assertEqual(n.quantities(0,3440),(3,9999))
  self.assertEqual(b.u32(n.slot(0),b.REGIONS['storage'][3]),b.u32(s.slot(0),b.REGIONS['storage'][3]))
 def test_reject_deleted(self):
  with self.assertRaises(b.SaveError):self.save.edit(1,4,{})
 def test_reject_over_cap(self):
  for key,q in [('1000',{'carry':999,'storage':999}),('3440',{'carry':3,'storage':10000}),('3000',{'carry':10,'storage':0})]:
   with self.assertRaises(b.SaveError):self.save.edit(0,4,{key:q})
 def test_reject_unowned_quest(self):
  for i in b.OWNED_ONLY:
   if not self.save.owned(0,i):
    with self.assertRaises(b.SaveError):self.save.edit(0,4,{str(i):{'carry':1,'storage':0}})
 def test_reject_unknown_item(self):
  with self.assertRaises(b.SaveError):self.save.edit(0,4,{'999999':{'carry':1,'storage':0}})
 def test_reject_corruption(self):
  d=bytearray(self.original);d[0x400]^=1
  with self.assertRaises(b.SaveError):b.Save(d)
 def test_reject_wrong_account(self):
  with self.assertRaises(b.SaveError):b.Save(self.original,123)
 def test_sen_bounds(self):
  for v in [-1,b.SEN_LIMIT+1,True,1.5]:
   with self.assertRaises(b.SaveError):self.save.edit(0,v,{})
 def test_idempotent(self):
  plan=self.save.maximum_plan(0);out,_=self.save.edit(0,b.SEN_LIMIT,plan);again,c=b.Save(out).edit(0,b.SEN_LIMIT,plan);self.assertEqual(out,again);self.assertEqual(c,[])
 def test_apply_without_history_chinese_path(self):
  with tempfile.TemporaryDirectory(prefix='资源修改测试_') as t:
   root=Path(t);p=root/str(ACCOUNT)/'S0000.sl2';p.parent.mkdir();p.write_bytes(self.original)
   with patch.object(b,'ROOT',root),patch.object(b,'game_running',return_value=False):
    changes=b.apply(p,b.sha(self.original),0,100,{'3440':{'carry':3,'storage':9999}})
   result=b.Save(p.read_bytes(),ACCOUNT)
   self.assertEqual(result.quantities(0,3440),(3,9999));self.assertEqual(b.u32(result.slot(0),b.SEN),100);self.assertTrue(changes)
   self.assertEqual(sorted(str(f.relative_to(root)) for f in root.rglob('*') if f.is_file()),[str(p.relative_to(root))])
 def test_running_game_refused(self):
  with patch.object(b,'game_running',return_value=True):
   with self.assertRaises(b.SaveError):b.apply(Path(str(ACCOUNT))/'S0000.sl2',b.sha(self.original),0,4,{})
 def test_changed_snapshot_refused(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/str(ACCOUNT)/'S0000.sl2';p.parent.mkdir();p.write_bytes(self.original)
   with patch.object(b,'game_running',return_value=False):
    with self.assertRaises(b.SaveError):b.apply(p,'wrong',0,4,{})
   self.assertEqual(p.read_bytes(),self.original)
 def test_apply_noop_no_history(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/str(ACCOUNT)/'S0000.sl2';p.parent.mkdir();p.write_bytes(self.original)
   with patch.object(b,'game_running',return_value=False):self.assertEqual(b.apply(p,b.sha(self.original),0,0,{}),[])
   self.assertEqual(list(p.parent.iterdir()),[p]);self.assertEqual(p.read_bytes(),self.original)
 def test_game_started_before_write_refused(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/str(ACCOUNT)/'S0000.sl2';p.parent.mkdir();p.write_bytes(self.original)
   with patch.object(b,'game_running',side_effect=[False,True]):
    with self.assertRaises(b.SaveError):b.apply(p,b.sha(self.original),0,100,{})
   self.assertEqual(p.read_bytes(),self.original);self.assertEqual(list(p.parent.iterdir()),[p])
 def test_failed_replace_cleans_temporary_file(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'S0000.sl2';p.write_bytes(self.original)
   with patch.object(b.os,'replace',side_effect=PermissionError('blocked')):
    with self.assertRaises(PermissionError):b.atomic_write(p,b'changed')
   self.assertEqual(p.read_bytes(),self.original);self.assertEqual(list(p.parent.iterdir()),[p])
 def test_full_inventory_insertion_refused(self):
  p=bytearray(self.save.slot(0));start,size,index,count=b.REGIONS['carry']
  row=self.save.records(0,'carry')[3440][0];p[row:row+16]=bytes(16)
  for o in range(start,start+0x1000,16):
   if not b.u32(p,o):struct.pack_into('<IIII',p,o,0x80801000+(o-start)//16,100,1,0)
  occupied=sum(bool(b.u32(p,o)) for o in range(start,start+size,16));b.put32(p,count,occupied)
  e=self.save.entries[0];data=bytearray(self.original);data[e.payload:e.payload+e.length]=p;data[e.offset:e.offset+16]=hashlib.md5(p).digest();s=b.Save(data)
  with self.assertRaises(b.SaveError):s.edit(0,4,{'3440':{'carry':3,'storage':9999}})
 def test_quantity_key_order(self):
  out,_=self.save.edit(0,4,{'3440':{'storage':123,'carry':2}})
  self.assertEqual(b.Save(out).quantities(0,3440),(2,123))

if __name__=='__main__':unittest.main(verbosity=2)
