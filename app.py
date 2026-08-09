from datetime import datetime, timedelta, timezone
import os
from flask import Flask, jsonify, render_template, request
import requests

app = Flask(__name__)


# --- PEMERIKSA STATUS SAKELAR VERCEL ---
@app.before_request
def check_status():
  # Membaca variabel secara langsung setiap ada request masuk
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
GOOGLE_SHEET_URL = 'https://script.google.com/macros/s/AKfycbyn88ANfRmR2M5knaX88Fkd_ALbp8jE1w6giz1Vsme8tuiQ8Zm-DtYgVBqU0wWRhKsc/exec'

# Memori RAM sementara untuk mencatat siswa yang sudah absen
sudah_absen = set()

# ⏰ ZONA WAKTU INDONESIA BARAT (WIB / UTC+7)
WIB = timezone(timedelta(hours=7))


@app.route('/')
def home():
  return render_template('index.html')


@app.route('/get_riwayat', methods=['GET'])
def get_riwayat():
  try:
    response = requests.get(GOOGLE_SHEET_URL)
    return jsonify(response.json())
  except Exception as e:
    return jsonify([])


@app.route('/proses_absen', methods=['POST'])
def proses_absen():
  # 1. Mengambil waktu real-time sesuai WIB
  sekarang = datetime.now(WIB)
  tanggal = sekarang.strftime('%Y-%m-%d')
  waktu = sekarang.strftime('%H:%M')  # Format 24 jam (misal 11:25)

  # 2. Batas waktu absen harian (atur sesuai kebutuhan, misal 23:59 atau 09:00)
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

    # 3. Kunci Absen Harian (TANGGAL + DATA QR)
    # Memastikan siswa bisa absen lagi saat tanggal berganti esok hari
    kunci_absen_hari_ini = f'{tanggal}|{data}'

    if kunci_absen_hari_ini in sudah_absen:
      return jsonify({
          'status': 'warning',
          'message': f'⚠️ {nama} sudah absen hari ini!',
      })

    sudah_absen.add(kunci_absen_hari_ini)

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
