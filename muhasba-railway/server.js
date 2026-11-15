const http=require('http'),fs=require('fs'),path=require('path');
const KEY=process.env.ANTHROPIC_API_KEY,MODEL=process.env.MODEL||'claude-sonnet-5-5',PASS=process.env.APP_PASSWORD||'',PORT=process.env.PORT||3000;
const PROMPT="ده سكان صفحة من ملف سركيهات سيارات (شركة أوراسكوم). ارجع JSON فقط بدون أي كلام آخر.\nلو الصفحة سركي سيارة (جدول أيام الشهر وعنوانه \"سرك ايجار سيارات\" وفيه الفئة واجمالي الدورات الفردية) ارجع:\n{\"is_sarki\":true,\"type\":\"نوع السيارة (مثلا اتوبيس / ميكروباص مكيف / ميني باص)\",\"route\":\"القيمة المكتوبة جوه الخانة اللي عليها عنوان \\\"خط السير\\\" في الصف العلوي من الجدول، وهي الخانة الموجودة على يسار خانة \\\"كود المشروع 578\\\" (مثلا رأس الحكمة أو الضبعة أو القاهرة أو مطروح). ممنوع تاخد الخط من السطر اللي تحتها اللي مكتوب فيه \\\"خط - الموقع - العودة\\\"، وممنوع تاخده من اسم المشروع أو من أي مكان تاني في الصفحة\",\"rate\":رقم الفئة,\"rounds\":رقم اجمالي الدورات الفردية,\"total\":رقم اجمالي قيمة السركي,\"car\":\"رقم/اسم السائق أو السيارة\"}\nلو الصفحة غير ذلك (قائمة أسماء ركاب أو غيرها) ارجع {\"is_sarki\":false}.\nالفئة هي الرقم المكتوب بخط كبير تحت اسم السائق (زي 4950.00 أو 6285.00 أو 2750.00) وليست إجمالي السركي. خط السير هو أول قيمة مكتوبة في أعلى الصفحة جنب عنوان \"خط السير\" مباشرة. لو مكتوب جنبها كلمة اسبوعي سيبها زي ما هي.\nالأرقام أرقام إنجليزية بدون فواصل. لو رقم مش واضح ارجع null.";
const page=()=>fs.readFileSync(path.join(__dirname,'public','index.html'));
http.createServer(async(req,res)=>{
  if(req.method==='POST'&&req.url==='/api/read'){
    if(PASS&&req.headers['x-pass']!==PASS){res.writeHead(401);return res.end()}
    if(!KEY){res.writeHead(503,{'content-type':'application/json'});return res.end(JSON.stringify({error:true,code:'api_key_missing'}))}
    const ch=[];let n=0;
    for await(const c of req){n+=c.length;if(n>8e6){res.writeHead(413);return res.end()}ch.push(c)}
    try{
      const r=await fetch('https://api.anthropic.com/v1/messages',{method:'POST',
        headers:{'content-type':'application/json','x-api-key':KEY,'anthropic-version':'2023-06-01'},
        body:JSON.stringify({model:MODEL,max_tokens:600,messages:[{role:'user',content:[
          {type:'image',source:{type:'base64',media_type:'image/jpeg',data:Buffer.concat(ch).toString('base64')}},
          {type:'text',text:PROMPT}]}]})});
      if(!r.ok){console.error('API',r.status,await r.text());res.writeHead(r.status===429?429:502);return res.end()}
      const j=await r.json(),t=(j.content||[]).map(x=>x.text||'').join(''),m=t.match(/\{[\s\S]*\}/);
      res.writeHead(200,{'content-type':'application/json'});return res.end(m?m[0]:'{"error":true,"code":"invalid_json"}');
    }catch(e){console.error(e);res.writeHead(502);return res.end()}
  }
  if(req.url==='/health'){res.writeHead(200);return res.end('ok')}
  res.writeHead(200,{'content-type':'text/html; charset=utf-8'});res.end(page());
}).listen(PORT,()=>console.log('up on '+PORT));