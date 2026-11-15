import os,re,io,csv,uuid,json
from pathlib import Path
import fitz,pytesseract
from PIL import Image,ImageOps,ImageFilter
from fastapi import FastAPI,UploadFile,File,Form
from fastapi.responses import HTMLResponse,StreamingResponse,JSONResponse
app=FastAPI(title="نظام المحاسبة والمخالصة")
DATA=Path("/data"); DATA.mkdir(exist_ok=True)
DIGITS=str.maketrans("٠١٢٣٤٥٦٧٨٩٬٫","0123456789,.")
def norm(s): return re.sub(r"[ \\t]+"," ",(s or "").translate(DIGITS).replace("ـ","")).strip()
def num(s):
 try:
  m=re.search(r"\\d+(?:[.,]\\d+)?",norm(str(s)).replace(",",""))
  return float(m.group()) if m else None
 except: return None
def labeled(t,labels):
 for label in labels:
  m=re.search(label+r"\\s*[:：\\-]?\\s*([^\\n]+)",t,re.I)
  if m:return m.group(1).strip(" :-")
 return ""
def extract(t):
 t=norm(t)
 rounds=num(re.search(r"(?:عدد الدورات|عدد الدور|الدورات|دورات)\\s*[:：\\-]?\\s*([\\d.,]+)|([\\d.,]+)\\s*دورة",t,re.I).group(1) or re.search(r"(?:عدد الدورات|عدد الدور|الدورات|دورات)\\s*[:：\\-]?\\s*([\\d.,]+)|([\\d.,]+)\\s*دورة",t,re.I).group(2)) if re.search(r"(?:عدد الدورات|عدد الدور|الدورات|دورات)\\s*[:：\\-]?\\s*([\\d.,]+)|([\\d.,]+)\\s*دورة",t,re.I) else None
 price=num(labeled(t,["قيمة الدورة","سعر الدورة","سعر الدور"]))
 total=num(labeled(t,["الإجمالي","اجمالي","إجمالي","الاجمالى"]))
 ded=num(labeled(t,["الخصومات","الخصم","خصم"])) or 0
 supplier=labeled(t,["اسم المورد","المورد","المقاول"])
 vehicle=labeled(t,["نوع العربية","نوع السيارة","نوع المركبة"])
 route=labeled(t,["خط السير/البيان","خط السير","البيان","المسار"])
 calc=rounds*price if rounds is not None and price is not None else None
 gross=total if total is not None else (calc or 0)
 return dict(supplier=supplier,vehicle_type=vehicle,route=route,rounds=rounds,round_price=price,total=total,deductions=ded,calculated_total=calc,net=gross-ded)
@app.get("/",response_class=HTMLResponse)
def home():
 return HTML
@app.get("/health")
def health():return {"ok":True,"app":"نظام المحاسبة والمخالصة"}
@app.post("/api/process")
async def process(file:UploadFile=File(...),supplier_hint:str=Form(""),period:str=Form("")):
 if not file.filename.lower().endswith(".pdf"):return JSONResponse({"error":"ارفع ملف PDF فقط"},status_code=400)
 data=await file.read()
 if len(data)>50*1024*1024:return JSONResponse({"error":"حجم الملف أكبر من 50 ميجابايت"},status_code=413)
 doc=fitz.open(stream=data,filetype="pdf"); rows=[]
 for i,p in enumerate(doc):
  pix=p.get_pixmap(matrix=fitz.Matrix(2.2,2.2),alpha=False)
  im=Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
  im=ImageOps.autocontrast(ImageOps.grayscale(im)).filter(ImageFilter.SHARPEN)
  raw=pytesseract.image_to_string(im,lang="ara+eng",config="--oem 1 --psm 6")
  r=extract(raw)
  if supplier_hint and not r["supplier"]:r["supplier"]=supplier_hint
  r.update(page=i+1,raw_text=raw,status="needs_review" if not r["supplier"] or not r["route"] or r["rounds"] is None else "ok")
  rows.append(r)
 job=uuid.uuid4().hex[:12]
 result={"job":job,"filename":file.filename,"period":period,"rows":rows}
 (DATA/(job+".json")).write_text(json.dumps(result,ensure_ascii=False),encoding="utf-8")
 return result
@app.post("/api/report")
async def report(payload:dict):
 rows=payload.get("rows",[]); groups={}
 for r in rows:
  rounds=num(r.get("rounds")) or 0; price=num(r.get("round_price"))
  printed=num(r.get("total")); gross=printed if printed is not None else rounds*(price or 0)
  ded=num(r.get("deductions")) or 0
  r["final_total"]=gross;r["deductions"]=ded;r["net"]=gross-ded
  key=(r.get("supplier") or "غير محدد",r.get("vehicle_type") or "غير محدد",r.get("route") or "غير محدد")
  g=groups.setdefault(key,{"supplier":key[0],"vehicle_type":key[1],"route":key[2],"rounds":0,"gross":0,"deductions":0,"net":0,"items":0})
  g["rounds"]+=rounds;g["gross"]+=gross;g["deductions"]+=ded;g["net"]+=gross-ded;g["items"]+=1
 return {"title":"مذكرة محاسبة ومخالصة","period":payload.get("period",""),"groups":list(groups.values()),"grand":{"gross":sum(x["gross"] for x in groups.values()),"deductions":sum(x["deductions"] for x in groups.values()),"net":sum(x["net"] for x in groups.values())},"rows":rows}
@app.post("/api/csv")
async def csv_export(payload:dict):
 out=io.StringIO();w=csv.writer(out);w.writerow(["الصفحة","المورد","نوع العربية","خط السير/البيان","عدد الدورات","قيمة الدورة","الإجمالي","الخصومات","صافي المستحق"])
 for r in payload.get("rows",[]):w.writerow([r.get("page"),r.get("supplier"),r.get("vehicle_type"),r.get("route"),r.get("rounds"),r.get("round_price"),r.get("final_total",r.get("total")),r.get("deductions"),r.get("net")])
 return StreamingResponse(io.BytesIO(out.getvalue().encode("utf-8-sig")),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=settlement.csv"})
HTML="""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>إدارة المحاسبة والمخالصة</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f8;color:#182435;font-family:Tahoma,Arial,sans-serif}.top{background:#101e32;color:#fff;padding:24px max(5%,calc((100% - 1200px)/2));display:flex;justify-content:space-between;align-items:center}.brand{font-size:24px;font-weight:bold}.sub{color:#b9c7d8;margin-top:8px}.wrap{max-width:1200px;margin:28px auto;padding:0 18px}.hero,.card{background:white;border-radius:16px;padding:24px;margin-bottom:20px;box-shadow:0 6px 24px #172b4410}.hero{display:flex;justify-content:space-between;gap:24px;align-items:center}h1{margin:0 0 10px;font-size:26px}p{color:#68778b;line-height:1.8}.note{background:#eef4fb;padding:14px;border-radius:12px;max-width:340px}.drop{display:block;border:2px dashed #9aabc0;padding:34px;text-align:center;border-radius:14px;cursor:pointer}.drop input{display:none}.drop b{display:block;font-size:18px;margin:12px}.fields{display:flex;gap:14px;margin:18px 0}.fields label{flex:1;color:#526174}.fields input{display:block;width:100%;padding:12px;border:1px solid #d6dde6;border-radius:9px;margin-top:7px}button{border:0;border-radius:9px;padding:12px 20px;cursor:pointer;font-weight:bold}.primary{background:#1766b1;color:white}.secondary{background:#e9eef5;color:#24364c;margin-right:8px}.hidden{display:none}.tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:950px}th,td{padding:9px;border-bottom:1px solid #e5eaf0;text-align:right}th{background:#f3f6fa}td input{width:105px;padding:7px;border:1px solid #d8e0e9;border-radius:6px}.actions{margin-top:18px}.stats{display:flex;gap:12px;flex-wrap:wrap}.stat{background:#f1f5fa;padding:14px;border-radius:10px;min-width:160px}.stat b{display:block;font-size:20px;margin-top:8px}.busy{padding:20px;color:#1766b1}@media(max-width:650px){.hero,.fields{display:block}.note{margin-top:16px}.fields label{display:block;margin-bottom:12px}.top{padding:20px}.brand{font-size:19px}}</style></head><body><header class="top"><div><div class="brand">إدارة المحاسبة والمخالصة</div><div class="sub">رفع السراكي • مراجعة • محاسبة ومخالصة</div></div><span>نظام ويب</span></header><main class="wrap"><section class="hero"><div><h1>رفع PDF السراكي</h1><p>ارفع ملف السراكي الممسوح ضوئياً. تتم قراءة الصفحات على الخادم ثم تظهر البيانات للمراجعة قبل اعتماد الحساب.</p></div><div class="note"><b>تنبيه محاسبي</b><br>رقم السيارة غير مستخدم في الحسابات. خط السير والبيان عنصر أساسي في التجميع.</div></section><section class="card"><form id="f"><label class="drop"><input id="pdf" type="file" accept=".pdf" required><b>اضغط لاختيار ملف PDF</b><span id="fname">لم يتم اختيار ملف</span></label><div class="fields"><label>المورد (اختياري)<input name="supplier_hint" placeholder="مثال: وطنية"></label><label>الفترة<input name="period" placeholder="مثال: أكتوبر 2026"></label></div><button class="primary">بدء معالجة السراكي</button></form><div id="busy" class="busy hidden">جاري قراءة صفحات الملف... لا تغلق الصفحة.</div></section><section id="review" class="card hidden"><h2>مراجعة البيانات المستخرجة</h2><p>صحح القيم قبل إنشاء المذكرة؛ نتائج الخط اليدوي تحتاج مراجعة بشرية.</p><div class="tablewrap"><table><thead><tr><th>صفحة</th><th>المورد</th><th>نوع العربية</th><th>خط السير / البيان</th><th>الدورات</th><th>قيمة الدورة</th><th>الإجمالي</th><th>الخصومات</th><th>الصافي</th><th>النص الخام</th></tr></thead><tbody id="rows"></tbody></table></div><div class="actions"><button class="primary" id="reportBtn">إنشاء المحاسبة والمخالصة</button><button class="secondary" id="csvBtn">تصدير Excel / CSV</button></div></section><section id="report" class="card hidden"><h2>مذكرة محاسبة ومخالصة</h2><div id="summary"></div><button class="secondary" onclick="print()">طباعة / حفظ PDF</button></section></main><script>
let data=null;const $=s=>document.querySelector(s);$('#pdf').onchange=()=>$('#fname').textContent=$('#pdf').files[0]?.name||'لم يتم اختيار ملف';
$('#f').onsubmit=async e=>{e.preventDefault();let file=$('#pdf').files[0];if(!file)return;$('#busy').classList.remove('hidden');$('#review').classList.add('hidden');let fd=new FormData(e.target);fd.append('file',file);try{let r=await fetch('/api/process',{method:'POST',body:fd}),j=await r.json();if(!r.ok)throw Error(j.error||'تعذرت المعالجة');data=j;renderRows();$('#review').classList.remove('hidden')}catch(err){alert(err.message)}finally{$('#busy').classList.add('hidden')}};
function renderRows(){ $('#rows').innerHTML='';data.rows.forEach((r,i)=>{let tr=document.createElement('tr');let fields=['page','supplier','vehicle_type','route','rounds','round_price','total','deductions'];tr.innerHTML=fields.map(k=>'<td>'+(k==='page'?r[k]:'<input data-i="'+i+'" data-k="'+k+'" value="'+String(r[k]??'').replaceAll('"','&quot;')+'">')+'</td>').join('')+'<td class="net">'+(r.net??'')+'</td><td><details><summary>عرض</summary><pre style="white-space:pre-wrap;max-width:250px">'+(r.raw_text||'').replaceAll('<','&lt;')+'</pre></details></td>';$('#rows').append(tr)});document.querySelectorAll('#rows input').forEach(x=>x.onchange=()=>{let r=data.rows[+x.dataset.i];r[x.dataset.k]=x.value;let gross=Number(r.total)||Number(r.rounds)*Number(r.round_price)||0;r.net=gross-(Number(r.deductions)||0);x.closest('tr').querySelector('.net').textContent=r.net})}
$('#reportBtn').onclick=async()=>{let r=await fetch('/api/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});let j=await r.json();$('#report').classList.remove('hidden');$('#summary').innerHTML='<p>الفترة: '+(j.period||'—')+'</p><div class="stats">'+[['الإجمالي',j.grand.gross],['الخصومات',j.grand.deductions],['صافي المستحق',j.grand.net]].map(x=>'<div class="stat">'+x[0]+'<b>'+x[1].toLocaleString('en-US')+' ج.م</b></div>').join('')+'</div><h3>تفصيل الموردين وخطوط السير</h3><div class="tablewrap"><table><tr><th>المورد</th><th>نوع العربية</th><th>خط السير</th><th>الدورات</th><th>الإجمالي</th><th>الخصومات</th><th>الصافي</th></tr>'+j.groups.map(g=>'<tr>'+[g.supplier,g.vehicle_type,g.route,g.rounds,g.gross,g.deductions,g.net].map(v=>'<td>'+v+'</td>').join('')+'</tr>').join('')+'</table></div>';window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'})};
$('#csvBtn').onclick=async()=>{let r=await fetch('/api/csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});let b=await r.blob(),u=URL.createObjectURL(b),a=document.createElement('a');a.href=u;a.download='settlement.csv';a.click();URL.revokeObjectURL(u)};
</script></body></html>"""
