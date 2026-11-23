# 🏨 Hotel LinkEX — Backend API Engine

نظام إدارة وحجوزات الفنادق والوحدات السكنية والشاليهات المبني بأحدث معايير هندسة البرمجيات الخلفية (Modular Monolith) باستخدام **Django 5.1** و **Django Ninja**.

---

## 🚀 المميزات المعمارية الرئيسية (Key Features)

1. **فصل فئات الغرف عن الوحدات الفعلية (Room Types vs Units):**
   - دعم حجز فئة الغرفة في الفنادق مع التسكين التلقائي أو اليدوي برقم الغرفة عند الدخول (Check-in).
   - دعم حجز الوحدات المستقلة مباشرة (الشاليهات والفلل والشقق).
2. **محرك توفر ومخزون يومي فائق السرعة $O(1)$:**
   - جدول مخزون يومي ذري (`RoomTypeInventory`) لمنع الـ Full Table Scans وتوفير أداء فوري لفحص التوفر.
3. **منع الحجز المزدوج (Zero Double-Booking Guarantee):**
   - حماية الصفقات والحجوزات المتزامنة عبر `transaction.atomic()` و `select_for_update()`.
4. **تفصيل أسعار الليالي والأسعار الموسمية الديناميكية (Nightly Breakdown):**
   - تسجيل دقيق لأسعار كل ليلة وتاريخها لضمان العدالة في سياسات الإلغاء والاسترجاع.
5. **فوترة ضريبية رسمية متوافقة مع زاتكا (ZATCA Phase 2 Compliant):**
   - توليد فواتير ضريبية مبسطة وقياسية مع بصمة رقمية مشفرة `SHA-256 Hash` وباركود `TLV Base64 QR Code`.
6. **محرك مالي متكامل لكشوفات الملاك (Finance & Owner Statements):**
   - احتساب إيرادات المباني، المصروفات التشغيلية، عمولة الإدارة، وصافي مستحقات الملاك دورياً.
7. **معالجة غير متزامنة بـ Celery & Redis:**
   - مهمات مجدولة لتحرير الغرف وإلغاء الحجوزات المعلقة غير المدفوعة تلقائياً.

---

## 🛠 التقنيات المستخدمة (Tech Stack)

- **Framework:** Django 5.1
- **API Engine:** Django Ninja (Pydantic V2 + OpenAPI 3.1)
- **Database:** PostgreSQL (مع دعم SQLite للتطوير المحلي)
- **Caching & Broker:** Redis
- **Task Queue:** Celery + Celery Beat
- **Authentication:** JWT (JSON Web Tokens) + RBAC & Property Scope Engine
- **Containerization:** Docker & Docker Compose

---

## 📁 هيكلية المشروع (Project Architecture)

```
Hotel_LinkEX/
├── backend/
│   ├── config/             # إعدادات النظام، Celery، وموجه NinjaAPI المركزي
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── celery.py
│   ├── apps/
│   │   ├── users/          # إدارة المستخدمين، الأدوار، الصلاحيات، ونطاق المباني
│   │   ├── properties/     # الفنادق، فئات الغرف، الوحدات، والتقويم والمخزون
│   │   ├── bookings/       # محرك الحجوزات، التحقق الذري، وتسجيل الدخول والخروج
│   │   ├── finance/        # المدفوعات، المصروفات، الفواتير الضريبية، وكشوفات الملاك
│   │   └── notifications/  # مهمات Celery الخلفية والتنبيهات
│   ├── Dockerfile
│   ├── requirements.txt
│   └── manage.py
├── docker-compose.yml       # تشغيل المنظومة بالكامل (Web + DB + Redis + Celery)
├── run.bat                 # تشغيل محلي سريع بنقرة واحدة (Windows)
├── .env.example            # نموذج متغيرات البيئة
└── README.md
```

---

## ⚡ البدء السريع (Quick Start)

### الخيار 1: التشغيل المحلي السريع (Local Development)

1. **إنشاء البيئة الافتراضية وتفعيلها:**
   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .\.venv\Scripts\Activate.ps1
   # Linux / macOS:
   source .venv/bin/activate
   ```

2. **تثبيت الحزم المطلوبة:**
   ```bash
   pip install -r backend/requirements.txt
   ```

3. **إعداد ملف البيئة:**
   قم بنسخ `backend/.env.example` إلى `backend/.env` وضبط الإعدادات المطلوبة:
   ```bash
   cp backend/.env.example backend/.env
   ```

4. **تطبيق ترحيل قواعد البيانات (Migrations):**
   ```bash
   python backend/manage.py migrate
   ```

5. **تشغيل خادم التطوير:**
   ```bash
   python backend/manage.py runserver
   ```
   *(أو بالنقر المزدوج على `run.bat` في نظام ويندوز)*.

---

### الخيار 2: التشغيل عبر Docker Compose

لتشغيل السيرفر وقاعدة بيانات PostgreSQL وخادم Redis وعامل Celery دفعة واحدة:
```bash
docker compose up --build
```

---

## 📖 توثيق الـ API التفاعلي (Swagger / OpenAPI)

بمجرد تشغيل السيرفر، يمكنك استعراض واختبار جميع مسارات الـ API (27 عملية) مباشرة عبر المتصفح:
- **Swagger UI:** `http://127.0.0.1:8000/api/docs`
- **لوحة تحكم جانغو:** `http://127.0.0.1:8000/admin/`

---

## 🔒 معايير الأمان (Security & Hardening)

- **IDOR Protection:** حماية كاملة لكافة بيانات الحجوزات والمدفوعات والفواتير بناءً على هوية المستخدم ونطاق صلاحيات المبنى (`Property Scope`).
- **Data Integrity:** قفل السجلات الحساسة باستخدام `select_for_update()` لمنع التعارض الزمني.
- **Password Policies:** تطبيق سياسات التحقق الصارمة لكلمات المرور وتشفير الرموز عبر JWT مع التحقق من نوع الرمز `type=access`.
