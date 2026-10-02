"""Sekiro Resource Modifier: offline resource editing with no retained history."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import backend as b

APP_NAME = 'Sekiro Resource Modifier'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry('1080x660')
        self.minsize(940,540)
        self.option_add('*Font', ('Microsoft YaHei UI',10))
        self.save=None
        self.current={}
        self.targets={}
        self.slots={}
        self.editing_key=None
        self.changing_fields=False
        style=ttk.Style(self)
        style.theme_use('clam')
        style.configure('Treeview',rowheight=28)
        style.configure('Treeview.Heading',font=('Microsoft YaHei UI',10,'bold'))
        outer=ttk.Frame(self,padding=15)
        outer.pack(fill='both',expand=True)
        ttk.Label(outer,text=APP_NAME,font=('Microsoft YaHei UI',19,'bold')).pack(anchor='w')
        top=ttk.Frame(outer)
        top.pack(fill='x')
        ttk.Label(top,text='游戏数据').pack(side='left')
        self.path=tk.StringVar()
        found=[str(p) for p in b.find_saves()]
        self.pathbox=ttk.Combobox(top,textvariable=self.path,values=found,state='readonly')
        self.pathbox.pack(side='left',fill='x',expand=True,padx=(8,0))
        self.pathbox.bind('<<ComboboxSelected>>',lambda e:self.load())
        opts=ttk.Frame(outer)
        opts.pack(fill='x',pady=10)
        ttk.Label(opts,text='存档').pack(side='left')
        self.slotvar=tk.StringVar()
        self.slotbox=ttk.Combobox(opts,textvariable=self.slotvar,width=37,state='readonly')
        self.slotbox.pack(side='left',padx=8)
        self.slotbox.bind('<<ComboboxSelected>>',lambda e:self.populate())
        ttk.Label(opts,text='钱币（Sen）').pack(side='left',padx=(15,4))
        self.sen=tk.StringVar()
        ttk.Entry(opts,textvariable=self.sen,width=12).pack(side='left')
        self.maxvar=tk.BooleanVar(value=False)
        ttk.Checkbutton(opts,text='全部填允许上限',variable=self.maxvar,command=self.maximum).pack(side='right')
        mid=ttk.Frame(outer)
        mid.pack(fill='both',expand=True)
        cols=('group','name','current_c','current_s','target_c','target_s','cap')
        self.tree=ttk.Treeview(mid,columns=cols,show='headings',selectmode='browse')
        self.tree.pack(side='left',fill='both',expand=True)
        for col,label,width in zip(cols,['分类','物品','随身当前','仓库当前','随身目标','仓库目标','上限：随身/仓库'],[80,200,90,90,90,90,150]):
            self.tree.heading(col,text=label)
            self.tree.column(col,width=width,minwidth=50,anchor='center' if col != 'name' else 'w')
        scroll=ttk.Scrollbar(mid,orient='vertical',command=self.tree.yview)
        scroll.pack(side='right',fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.tag_configure('protected',foreground='#8c8c8c')
        self.tree.bind('<<TreeviewSelect>>',self.select)
        self.tree.bind('<Double-1>',lambda e:self.centry.focus_set())
        edit=ttk.Frame(outer)
        edit.pack(fill='x',pady=12)
        self.selected=tk.StringVar(value='请选择物品')
        ttk.Label(edit,textvariable=self.selected,width=25).pack(side='left')
        self.carry=tk.StringVar()
        self.store=tk.StringVar()
        ttk.Label(edit,text='随身').pack(side='left')
        self.centry=ttk.Entry(edit,textvariable=self.carry,width=9,state='disabled')
        self.centry.pack(side='left',padx=5)
        ttk.Label(edit,text='仓库').pack(side='left')
        self.sentry=ttk.Entry(edit,textvariable=self.store,width=9,state='disabled')
        self.sentry.pack(side='left',padx=5)
        self.carry.trace_add('write',self.field_changed)
        self.store.trace_add('write',self.field_changed)
        foot=ttk.Frame(outer)
        foot.pack(fill='x',pady=(0,5))
        ttk.Button(foot,text='保存',command=self.apply).pack(side='right',ipadx=24)
        if found:
            self.path.set(found[0])
            self.load()
        else:
            self.error(b.SaveError('未找到有效存档。请先在游戏中创建存档并退出，然后重新打开程序。'))

    def error(self,ex):
        messagebox.showerror(APP_NAME,str(ex),parent=self)

    def load(self):
        try:
            p=Path(self.path.get())
            data=p.read_bytes()
            self.save=b.Save(data,int(p.parent.name))
            self.expected=b.sha(data)
            self.slots={self.save.slot_label(i):i for i in self.save.active}
            self.slotbox['values']=list(self.slots)
            if not self.slots:raise b.SaveError('没有可编辑的有效存档。')
            if self.slotvar.get() not in self.slots:self.slotvar.set(next(iter(self.slots)))
            self.populate()
        except Exception as e:
            self.save=None
            self.editing_key=None
            self.tree.delete(*self.tree.get_children())
            self.centry.configure(state='disabled')
            self.sentry.configure(state='disabled')
            self.error(e)

    def slot(self):
        if not self.save:raise b.SaveError('请先读取有效游戏数据。')
        return self.slots[self.slotvar.get()]

    def populate(self):
        slot=self.slot()
        self.editing_key=None
        self.changing_fields=True
        self.carry.set('')
        self.store.set('')
        self.changing_fields=False
        self.centry.configure(state='disabled')
        self.sentry.configure(state='disabled')
        self.selected.set('请选择物品')
        self.maxvar.set(False)
        self.tree.delete(*self.tree.get_children())
        self.targets={}
        self.current={}
        self.sen.set(str(b.u32(self.save.slot(slot),b.SEN)))
        for group,ids in b.GROUPS.items():
            for id in ids:
                key=str(id)
                owned=self.save.owned(slot,id)
                caps=self.save.caps(slot,id)
                q=self.save.quantities(slot,id)
                blocked=id in b.OWNED_ONLY and not owned
                self.current[key]=q
                self.targets[key]=dict(zip(b.REGIONS,q))
                self.tree.insert('','end',iid=key,values=(group,b.CATALOG[key]['name'] or f'物品 {id}',*q,*q,f'{caps[0]}/{caps[1]}'),tags=('protected',) if blocked else ())

    def row_values(self):
        key=self.editing_key
        if key is None:return None
        id=int(key)
        slot=self.slot()
        if id in b.OWNED_ONLY and not self.save.owned(slot,id):return None
        try:q=(int(self.carry.get()),int(self.store.get()))
        except ValueError:raise b.SaveError('随身和仓库数量必须是整数。')
        caps=self.save.caps(slot,id)
        if any(not 0<=v<=c for v,c in zip(q,caps)):
            raise b.SaveError(f'{b.CATALOG[key]["name"]}：数量必须分别处于 0～{caps[0]} 和 0～{caps[1]}。')
        return key,dict(zip(b.REGIONS,q))

    def commit_selected(self):
        row=self.row_values()
        if row:
            key,q=row
            self.targets[key]=q
            self.repaint(key)

    def field_changed(self,*args):
        if self.changing_fields or self.editing_key is None:return
        self.maxvar.set(False)
        try:
            self.commit_selected()
        except b.SaveError:
            pass

    def select(self,e=None):
        sel=self.tree.selection()
        if not sel:return
        key=sel[0]
        if key==self.editing_key:return
        try:self.commit_selected()
        except b.SaveError as ex:
            if self.editing_key:self.tree.selection_set(self.editing_key)
            self.error(ex)
            return
        self.editing_key=key
        self.selected.set(b.CATALOG[key]['name'])
        q=self.targets[key]
        self.changing_fields=True
        self.carry.set(str(q['carry']))
        self.store.set(str(q['storage']))
        self.changing_fields=False
        blocked=int(key) in b.OWNED_ONLY and not self.save.owned(self.slot(),int(key))
        state='disabled' if blocked else 'normal'
        self.centry.configure(state=state)
        self.sentry.configure(state=state)

    def repaint(self,key):
        values=list(self.tree.item(key,'values'))
        q=self.targets[key]
        values[4:6]=[q['carry'],q['storage']]
        self.tree.item(key,values=values)

    def maximum(self):
        if not self.maxvar.get():return
        try:
            self.sen.set(str(b.SEN_LIMIT))
            for key,q in self.save.maximum_plan(self.slot()).items():
                self.targets[key]=q
                self.repaint(key)
            if self.editing_key:
                q=self.targets[self.editing_key]
                self.changing_fields=True
                self.carry.set(str(q['carry']))
                self.store.set(str(q['storage']))
                self.changing_fields=False
        except Exception as e:self.error(e)

    def plan(self):
        self.commit_selected()
        slot=self.slot()
        items={k:v for k,v in self.targets.items() if int(k) not in b.OWNED_ONLY or self.save.owned(slot,int(k))}
        try:sen=int(self.sen.get())
        except ValueError:raise b.SaveError('钱币数量必须是整数。')
        self.save.edit(slot,sen,items)
        return slot,sen,items

    def apply(self):
        try:
            slot,sen,items=self.plan()
            changes=b.apply(Path(self.path.get()),self.expected,slot,sen,items)
            self.load()
            if self.save:messagebox.showinfo(APP_NAME,'已保存。',parent=self)
        except Exception as e:self.error(e)


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--self-test-report':
        from smoke_test import run
        raise SystemExit(run(sys.argv[2]))
    App().mainloop()
