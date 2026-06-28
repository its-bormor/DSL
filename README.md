# 🩺 คู่มือติดตั้งระบบลงชื่อเข้าเวรแพทย์ (Discord Shift Bot - Google Sheets Cloud Version)

ระบบบันทึกเวลาปฏิบัติงานของแพทย์ (เข้าเวร/ออกเวร) และแสดงรายชื่อพร้อมแดชบอร์ดสรุปผลแบบเรียลไทม์ใน Discord โดยบันทึกข้อมูลทั้งหมดลง **Google Sheets** และเปิดรันบนคลาวด์ตลอด 24 ชั่วโมงฟรี 100%

---

## 📋 สารบัญขั้นตอนการติดตั้ง
1. [การตั้งค่า Google Sheets API และเตรียมชีต](#1-การตั้งค่า-google-sheets-api-และเตรียมชีต)
2. [การตั้งค่า Discord Bot Token](#2-การตั้งค่า-discord-bot-token)
3. [การทดสอบบอทในเครื่องคอมพิวเตอร์ของคุณ (Local Test)](#3-การทดสอบบอทในเครื่องคอมพิวเตอร์ของคุณ-local-test)
4. [การอัปโหลดโค้ดขึ้น GitHub (เก็บข้อมูลส่วนตัวปลอดภัย)](#4-การอัปโหลดโค้ดขึ้น-github-เก็บข้อมูลส่วนตัวปลอดภัย)
5. [การนำบอทรันขึ้นคลาวด์ Render.com ฟรี 24 ชั่วโมง](#5-การนำบอทรันขึ้นคลาวด์-rendercom-ฟรี-24-ชั่วโมง)
6. [การทำตัวช่วยป้องกันบอทหลับ (UptimeRobot)](#6-การทำตัวช่วยป้องกันบอทหลับ-uptimerobot)

---

## 1. การตั้งค่า Google Sheets API และเตรียมชีต

บอทจำเป็นต้องใช้สิทธิ์ในการเขียนข้อมูลลง Google Sheets ของคุณผ่านระบบ API ของ Google Cloud:

### 1.1 สร้างไฟล์คีย์ Credentials JSON
1. เข้าไปที่ [Google Cloud Console](https://console.cloud.google.com/) (ล็อกอินด้วยบัญชี Gmail ของคุณ)
2. กดสร้างโปรเจกต์ใหม่ **"New Project"** ตั้งชื่อเช่น `Discord-Shift-Bot` แล้วกด **Create**
3. ค้นหาแถบเมนูด้านบนพิมพ์คำว่า **"Google Sheets API"** คลิกเข้าไปแล้วกดปุ่ม **Enable**
4. ทำซ้ำข้อ 3 โดยค้นหาคำว่า **"Google Drive API"** แล้วกด **Enable**
5. ไปที่แถบเมนูด้านซ้าย เลือก **APIs & Services** -> **Credentials**
6. คลิกปุ่ม **"+ CREATE CREDENTIALS"** ด้านบน แล้วเลือก **Service Account**
7. กรอกข้อมูลชื่อ Service Account เช่น `discord-bot` จากนั้นกด **CREATE AND CONTINUE** และกด **DONE**
8. ในตารางหัวข้อ *Service Accounts* ด้านล่าง ให้คลิกที่ไอคอนดินสอ หรือคลิกที่อีเมลบัญชีบริการที่เพิ่งสร้างขึ้น
9. ไปที่แท็บ **Keys** -> คลิกปุ่ม **Add Key** -> เลือก **Create new key**
10. เลือกประเภทเป็น **JSON** แล้วกด **Create**
11. ระบบจะดาวน์โหลดไฟล์ลงคอมพิวเตอร์ของคุณ ให้เปลี่ยนชื่อไฟล์นี้เป็น `credentials.json` และนำไปวางไว้ในโฟลเดอร์โปรเจกต์ `discord-shift-bot`
12. **คัดลอกอีเมลของ Service Account** ไว้ (เช่น `discord-bot@xxxxxx.iam.gserviceaccount.com` ซึ่งสามารถดูได้ในไฟล์ JSON หรือหน้าเว็บ Credentials)

### 1.2 สร้างและแชร์สิทธิ์ Google Sheet
1. เปิดหน้าเว็บ [Google Sheets](https://docs.google.com/spreadsheets) และสร้างสเปรดชีตว่างขึ้นมาใหม่ (Blank Sheet)
2. กดปุ่ม **"แชร์" (Share)** สีน้ำเงินมุมบนขวา
3. วาง **อีเมล Service Account** ที่คัดลอกมาจากขั้นตอนก่อนหน้าลงไป กำหนดสิทธิ์ให้เป็น **"เอディเตอร์" (Editor / ผู้เขียนร่วม)** แล้วกดแชร์
4. คัดลอก **Google Sheet ID** จาก URL บนเบราว์เซอร์ของคุณ
   * ตัวอย่าง URL: `https://docs.google.com/spreadsheets/d/1X2y3z4w5v6u7t8s9r_Example_ID/edit`
   * ไอดีของชีตคุณคือค่าระหว่าง `/d/` และ `/edit` (ในที่นี้คือ `1X2y3z4w5v6u7t8s9r_Example_ID`)

---

## 2. การตั้งค่า Discord Bot Token
1. เข้าไปที่ [Discord Developer Portal](https://discord.com/developers/applications) กด **"New Application"** ตั้งชื่อบอท
2. ไปที่เมนู **Bot** กด **Add Bot**
3. เปิดสิทธิ์ **Server Members Intent** และ **Message Content Intent** ในหัวข้อ Privileged Gateway Intents แล้วกดเซฟ
4. กด **Reset Token** และคัดลอก Token เก็บไว้ใช้งาน
5. ไปที่เมนู **OAuth2** -> **URL Generator** เลือกสิทธิ์ `bot` และ `applications.commands`
6. ในแถบสิทธิ์ด้านล่าง ติ๊กเลือกสิทธิ์ส่งข้อความ ส่งไฟล์ (Attach Files) และ Embed Links นำลิงก์ URL ที่สร้างขึ้นไปเปิดรันบนเบราว์เซอร์เพื่อเชิญบอทเข้าห้องดิสคอร์ดของคุณ

---

## 3. การทดสอบบอทในเครื่องคอมพิวเตอร์ของคุณ (Local Test)
1. เปิด PowerShell หรือ Terminal ในโฟลเดอร์โปรเจกต์ติดตั้งไลบรารี:
   ```bash
   pip install -r requirements.txt
   ```
2. คัดลอกและสร้างไฟล์ `.env` ขึ้นมาจากไฟล์ `.env.example`
3. กรอกข้อมูลความลับลงในไฟล์ `.env`:
   ```env
   DISCORD_TOKEN=โทเค็นบอทของคุณ
   GUILD_ID=ไอดีเซิร์ฟเวอร์ดิสคอร์ดของคุณ (ทำให้สแลชคอมมานด์อัปเดตทันที)
   LOG_CHANNEL_ID=ไอดีห้องที่ต้องการส่ง Log (เว้นว่างไว้หากไม่อยากใช้)
   GOOGLE_SHEET_ID=ไอดี Google Sheet ที่คัดลอกมาจากข้อ 1.2
   CREDENTIALS_JSON_PATH=credentials.json
   ```
4. รันคำสั่งเปิดใช้งานบอททดสอบ:
   ```bash
   python bot.py
   ```
5. เข้าดิสคอร์ดแล้วเปิดใช้งานสแลชคอมมานด์พิมพ์คำสั่ง `/setup` และ `/setup-dashboard` ในห้องแชทที่ต้องการ
6. ทดลองกดปุ่ม **เข้าเวร/ออกเวร** สังเกตว่าใน Google Sheets จะมีแผ่นงาน `shifts` และ `settings` เพิ่มขึ้นมา และมีแถวบันทึกเวลาอัปเดตลงไปโดยอัตโนมัติ!

---

## 4. การอัปโหลดโค้ดขึ้น GitHub (เก็บข้อมูลส่วนตัวปลอดภัย)

บอทนี้มีไฟล์ `.gitignore` ซึ่งบล็อกไม่ให้อัปโหลดไฟล์ความลับอย่าง `.env` และ `credentials.json` ขึ้นเว็บสาธารณะโดยเด็ดขาด ทำให้ปลอดภัยสูงสุด:

1. สมัครใช้งานและล็อกอินเข้า [GitHub](https://github.com/)
2. คลิกสร้างคลังเก็บโค้ดใหม่ **"New Repository"**
3. ตั้งชื่อโปรเจกต์ เลือกสิทธิ์การเข้าถึงเป็น **"Private" (ส่วนตัว - ห้ามแชร์สาธารณะ)** จากนั้นกดสร้าง
4. เปิด Command Prompt หรือ PowerShell ในโฟลเดอร์บอทแล้วรันคำสั่งเหล่านี้เพื่อผลักโค้ดขึ้น GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit with Google Sheets setup"
   git branch -M main
   git remote add origin https://github.com/ชื่อผู้ใช้ของคุณ/ชื่อโปรเจกต์ของคุณ.git
   git push -u origin main
   ```

---

## 5. การนำบอทรันขึ้นคลาวด์ Render.com ฟรี 24 ชั่วโมง

บอทมีเว็บเซิร์ฟเวอร์ Flask เล็ก ๆ ฝังตัวอยู่ภายใน ทำให้เราสามารถนำบอทขึ้นบริการ Render.com ฟรีในรูปแบบ "Web Service" ได้อย่างสมบูรณ์แบบ:

1. สมัครใช้งาน [Render.com](https://render.com/) โดยสมัครผ่านบัญชี GitHub ของคุณ
2. ในหน้าแดชบอร์ด Render คลิกปุ่ม **"New +"** -> เลือก **Web Service**
3. คอนเน็คคลังเก็บโค้ด GitHub ที่คุณเพิ่งอัปโหลดไป
4. ตั้งค่าหน้าเว็บติดตั้งบริการ:
   * **Name**: ตั้งชื่อบอทของคุณ (เช่น `hospital-shift-bot`)
   * **Region**: เลือกโซนใกล้ตัวเรา เช่น `Singapore`
   * **Runtime**: เลือกเป็น `Python`
   * **Build Command**: พิมพ์ `pip install -r requirements.txt`
   * **Start Command**: พิมพ์ `python bot.py`
   * **Instance Type**: ติ๊กเลือกประเภท **Free**
5. เลื่อนลงไปข้างล่างสุด คลิกที่ปุ่ม **Advanced** เพื่อตั้งค่าความลับ:
   * **Environment Variables (ตัวแปรระบบ)**: คลิก Add เพิ่มทีละตัวแปรตามสัญลักษณ์ดังนี้:
     * `DISCORD_TOKEN` = (โทเค็นบอทดิสคอร์ดของคุณ)
     * `GOOGLE_SHEET_ID` = (ไอดี Google Sheet ของคุณ)
     * `CREDENTIALS_JSON_PATH` = `credentials.json`
     * `GUILD_ID` = (ไอดีเซิร์ฟเวอร์ดิสคอร์ด)
     * `LOG_CHANNEL_ID` = (ไอดีห้อง log ถ้ามี)
   * **Secret Files (ไฟล์ลับ)**: คลิกสร้างไฟล์ลับ ตั้งชื่อไฟล์ว่า **`credentials.json`** จากนั้นเปิดไฟล์ `credentials.json` ในเครื่องคอมพิวเตอร์ของคุณ คัดลอกข้อความ JSON ทั้งหมดมาวางใส่ในช่องเนื้อหาของ Render แล้วกดตกลง
6. กดปุ่ม **"Deploy Web Service"** ด้านล่างสุด

*Render จะใช้เวลาดาวน์โหลดไลบรารีและทำการรันประมาณ 2-3 นาที เมื่อขึ้นไฟเขียวพร้อมข้อความ `Keep-alive web server started.` และ `Bot logged in as ...` แสดงว่าบอทของคุณย้ายไปอยู่บนคลาวด์ออนไลน์ 24 ชั่วโมงสำเร็จแล้ว! คุณสามารถปิดคอมพิวเตอร์ของคุณได้เลยครับ*

---

## 6. การทำตัวช่วยป้องกันบอทหลับ (UptimeRobot)

เนื่องจาก Render.com มีระบบประหยัดพลังงานสำหรับแผนบริการฟรี หากเว็บเซิร์ฟเวอร์ไม่ได้รับการเรียกเข้าใช้งานเกิน 15 นาที บอทจะปิดตัวชั่วคราว (เข้าสู่โหมดหลับ) เราจึงต้องใช้ระบบเรียกจิกบอทฟรีมาช่วยป้องกัน:

1. ไปที่เมนูหลักของเว็บบน Render คัดลอก URL บริการของคุณ (เช่น `https://hospital-shift-bot.onrender.com/`)
2. สมัครใช้งานฟรีที่ [UptimeRobot](https://uptimerobot.com/)
3. ในหน้าแดชบอร์ด UptimeRobot กดปุ่ม **"Add New Monitor"**
4. ตั้งค่ามอนิเตอร์:
   * **Monitor Type**: เลือกเป็น `HTTPS`
   * **Friendly Name**: ตั้งชื่อ เช่น `Shift Bot Keep-Alive`
   * **URL (or IP)**: วางลิงก์เว็บ Render ที่คัดลอกมาลงไป (ข้อ 1)
   * **Monitoring Interval**: เลือกความถี่ในการจิกเรียกเป็น **Every 5 minutes** (ทุก ๆ 5 นาที)
5. กดปุ่ม **Create Monitor** ยืนยันสำเร็จ

*เพียงเท่านี้ UptimeRobot จะคอยส่งสัญญาณเรียกเว็บของคุณทุก ๆ 5 นาที ทำให้ระบบ Render เข้าใจว่ามีผู้ใช้งานอยู่ตลอดเวลา บอทดิสคอร์ดของคุณก็จะออนไลน์ทำงาน 100% ฟรีตลอดชีพโดยไม่หลับใหลครับ!*
