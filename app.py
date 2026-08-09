from datetime import datetime, timedelta, timezone
import os
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

    # 🔍 CEK REAL-TIME KE GOOGLE SHEET
    # Mengambil data langsung dari Sheet saat ini
    try:
      res_sheet = requests.get(GOOGLE_SHEET_URL, timeout=5)
      riwayat = res_sheet.json() if res_sheet.status_code == 200 else []
    except Exception:
      riwayat = []

    # Cek apakah ID siswa sudah terdaftar di Sheet PADA TANGGAL HARI INI
    sudah_absen_di_sheet = any(
        str(item.get('id')) == str(id_user)
        and str(item.get('tanggal')) == tanggal
        for item in riwayat
        if isinstance(item, dict)
    )

    if sudah_absen_di_sheet:
      return jsonify({
          'status': 'warning',
          'message': f'⚠️ {nama} sudah absen hari ini!',
      })

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
      return jsonify(
          {'status': 'error', 'message': f'⚠️ Gagal menyimpan ke Sheet: {str(e)}'}
      )
  else:
    return jsonify({'status': 'error', 'message': '⚠️ Format QR Code salah!'})


if __name__ == '__main__':
  app.run(host='0.0.0.0', port=5000, debug=True)
