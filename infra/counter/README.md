# عداد الزوّار + Web Push — `elyoxe-cinema-counter`

مكدّس منفصل تماماً عن مكدّس الموقع (`elyoxe-cinema`) — ap-south-1، لا يلمس bucket الموقع ولا
توزيعات CloudFront ولا DNS.

## النشر
```bash
infra/counter/deploy.sh
```
يبني طبقة Web Push (تنزيل wheels جاهزة، بلا docker)، يولّد مفاتيح VAPID وسرّ `/stats` في SSM إذا
ما كانت موجودة، ثم `sam build && sam deploy --resolve-s3`. آمن يعاد تشغيله — كل خطوة idempotent.

## الموارد
- `elyoxe-cinema-metrics` (DynamoDB, on-demand) — عدّادات يومية `{d, k, n}`، `k` مثل `film#view`
  أو `_#return#2-7` أو `_#ttb#0-3s`.
- `elyoxe-cinema-uniques` (DynamoDB، TTL يومان) — هاش يومي مُعاد تدويره من الجهاز، لا معرّف عابر.
- `elyoxe-cinema-push-subs` (DynamoDB) — اشتراكات Web Push (`endpoint`, `p256dh`, `auth`, `topic`).
- HTTP API واحد: `POST /events`، `GET /stats?secret=…`، `POST|DELETE /push/subscribe`.
- Lambda مجدولة `elyoxe-cinema-push-weekly` — كل خميس 08:00 UTC (12:00 دبي).
- طبقة `elyoxe-cinema-webpush` (cryptography + py-vapid + http-ece + pywebpush).

## الخصوصية (مفروضة في الكود، لا بالوثيقة فقط)
- `ingest.py` لا يقرأ أبداً `requestContext.http.sourceIp` ولا يطبع الـ`event` الخام.
- لا `AccessLogSettings` على الـHTTP API — لا سجلات فيها IP.
- `uid` هاش يومي فقط، TTL يومان، لا يُقرأ إلا للعدّ (`Select: COUNT`).

## التفكيك (teardown)
```bash
aws cloudformation delete-stack --region ap-south-1 --stack-name elyoxe-cinema-counter
aws ssm delete-parameters --region ap-south-1 --names \
  /elyoxe/cinema/counter/vapid-public /elyoxe/cinema/counter/vapid-private /elyoxe/cinema/counter/stats-secret
```
الجدول والـLambdas والـAPI كلها تُحذف مع المكدّس (لا `DeletionPolicy: Retain` على أي شي هنا).
التكلفة المتوقعة داخل الطبقة المجانية: DynamoDB on-demand + Lambda + HTTP API عند هذا الحجم من
الزيارات تبقى تحت 1$/شهر تقريباً (لا NAT، لا VPC، لا S3 تخزين دائم غير zip الطبقة).
