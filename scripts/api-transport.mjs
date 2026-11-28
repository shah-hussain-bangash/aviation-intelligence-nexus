import https from 'node:https';
import {checkServerIdentity} from 'node:tls';
import {routing} from './runtime-config.mjs';

export function fetchApi(pathname,apiPort,config,options={}){
  const {apiHost}=routing(config);
  if(!config.localApiHttps)return fetch(`http://${apiHost}:${apiPort}${pathname}`,options);
  if(!config.localHttps||config.profile!=='test'||config.container||apiHost!=='127.0.0.1'||config.sessionCookie!=='ain_test_session'||!Buffer.isBuffer(config.backendTlsCertificate))throw new Error('Local API TLS unavailable.');
  return new Promise((resolve,reject)=>{
    const request=https.request(`https://${apiHost}:${apiPort}${pathname}`,{
      method:options.method||'GET',headers:options.headers,signal:options.signal,agent:false,
      ca:config.backendTlsCertificate,rejectUnauthorized:true,minVersion:'TLSv1.2',
      checkServerIdentity(host,certificate){
        const error=checkServerIdentity(host,certificate);
        if(error)return error;
        if(certificate.fingerprint256?.replaceAll(':','').toLowerCase()!==config.tlsPin)return new Error('Local API certificate rejected.');
      }
    },response=>{
      if(response.statusCode>=300&&response.statusCode<400){response.resume();reject(new Error('API redirects refused.'));return;}
      const chunks=[];let bytes=0;
      response.on('data',chunk=>{
        bytes+=chunk.length;
        if(bytes>1024*1024){response.destroy();reject(new Error('API response too large.'));return;}
        chunks.push(chunk);
      });
      response.on('error',reject);
      response.on('end',()=>{
        if(response.destroyed&&!response.complete)return;
        try{
          const headers=new Headers();
          for(let i=0;i<response.rawHeaders.length;i+=2)headers.append(response.rawHeaders[i],response.rawHeaders[i+1]);
          resolve(new Response(chunks.length?Buffer.concat(chunks):null,{status:response.statusCode,headers}));
        }catch(error){reject(error);}
      });
    });
    request.on('error',reject);
    if(options.body!==undefined&&options.body!==null)request.write(options.body);
    request.end();
  });
}
