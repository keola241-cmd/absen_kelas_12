from datetime import datetime, timedelta, timezone
import os
import time
from flask import Flask, jsonify, render_template, request
import requests

app = Flask(__name__)


# --- PEMERIKSA STATUS SAKELAR VERCEL ---
@app.before_request
def check_status():
  if os.environ.get('WEB_ACTIVE', 'TRUE').upper() != 'TRUE':
    return (
        """
        <div style="text-align:center; padding:50px; font-family:sans-serif;">
            <h1 style="color:red;">Akses Ditangguhkan ⚠️</h1>
            <p>Masa aktif aplikasi telah berakhir / menunggu konfirmasi pembayaran.</p>
            <p>Silakan hubungi Admin/Developer untuk mengaktifkan kembali.</p>
        </div>
        """,
        403,
    )


# ---------------------------------------

# 🔗 LINK GOOGLE APPS SCRIPT
GOOGLE_SHEET_URL = 'https://script.google.com/macros/s/AKfycbzSLboW2kX9DsD8PAMFkq4YzNesl5MnWyglaTM4UDSZpgBgJ3sjXnMsn5rAGr3Cq7MH/exec'

# ⏰ ZONA WAKTU INDONESIA BARAT (WIB / UTC+7)
WIB = timezone(timedelta(hours=7))

# RAM Cache untuk menyimpan timestamp scan terakhir (Mencegah spam scan ganda dalam hitungan detik)
scan_terakhir = {}


@app.route('/')
def home():
  return render_template('index.html')


@app.route('/get_riwayat', methods=['GET'])
def get_riwayat():
  try:
    response = requests.get(GOOGLE_SHEET_URL, timeout=5)
    return jsonify(response.json())
  except Exception as e:
    return jsonify([])


@app.route('/proses_absen', methods=['POST'])
def proses_absen():
  sekarang = datetime.now(WIB)
  tanggal = sekarang.strftime('%Y-%m-%d')
  waktu = sekarang.strftime('%H:%M')

  batas_waktu = sekarang.replace(
      hour=23, minute=59, second=59, microsecond=0
  )

  if sekarang > batas_waktu:
    return jsonify({
        'status': 'ditutup',
        'message': f"❌ Absen ditutup! Sekarang jam {waktu}.",
    })

  data = request.json.get('qr_data', '')
  data_split = data.split('|')

  if len(data_split) == 4:
    id_user, nama, kelas, role = data_split
    kunci_absen = f'{tanggal}|{id_user}'
    sekarang_ts = time.time()

    # 1. ANTI-SPAM (Mencegah scan beruntun / double-click dalam jeda < 5 detik)
    if (
        kunci_absen in scan_terakhir
        and (sekarang_ts - scan_terakhir[kunci_absen]) < 5
    ):
      return jsonify({
          'status': 'warning',
          'message': f'⚠️ {nama} baru saja scan! Harap tunggu sebentar.',
      })

    # Catat waktu scan terbaru di RAM
    scan_terakhir[kunci_absen] = sekarang_ts

    # 2. CEK DATA REAL-TIME DI GOOGLE SHEET
    # Mengambil data aktual yang ADA di Sheet saat ini
    kunci_sheet = set()
    try:
      res_sheet = requests.get(GOOGLE_SHEET_URL, timeout=3)
      if res_sheet.status_code == 200:
        riwayat = res_sheet.json()
        kunci_sheet = {
            f"{item.get('tanggal')}|{item.get('id')}"
            for item in riwayat
            if isinstance(item, dict)
        }
    except Exception:
      pass

    # 3. JIKA SUDAH ADA DI GOOGLE SHEET HARI INI -> TOLAK (JATAH 1x ABSEN PER HARI)
    if kunci_absen in kunci_sheet:
      return jsonify({
          'status': 'warning',
          'message': f'⚠️ {nama} sudah absen hari ini!',
      })

    # 4. JIKA BELUM ADA (Atau jika data di Sheet sudah dihapus Admin) -> SIMPAN DATA
    payload = {
        'id': id_user,
        'nama': nama,
        'kelas': kelas,
        'role': role,
        'tanggal': tanggal,
        'waktu': waktu,
    }

    try:
      requests.post(GOOGLE_SHEET_URL, json=payload, allow_redirects=True)
      return jsonify({
          'status': 'success',
          'message': f'✅ {nama} Berhasil Absen!',
          'siswa': payload,
      })
    except Exception as e:
      # Jika server gagal menyimpan ke Sheet, reset pengunci spam
      scan_terakhir.pop(kunci_absen, None)
      return jsonify({
          'status': 'error',
          'message': f'⚠️ Gagal menyimpan ke Sheet: {str(e)}',
      })
  else:
    return jsonify({'status': 'error', 'message': '⚠️ Format QR Code salah!'})


if __name__ == '__main__':
  app.run(host='0.0.0.0', port=5000, debug=True)
