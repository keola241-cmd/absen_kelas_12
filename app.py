from datetime import datetime, timedelta, timezone
import os
import threading
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

GOOGLE_SHEET_URL = 'https://script.google.com/macros/s/AKfycbyn88ANfRmR2M5knaX88Fkd_ALbp8jE1w6giz1Vsme8tuiQ8Zm-DtYgVBqU0wWRhKsc/exec'

# Storage RAM: Key -> timestamp_terakhir_scan
sudah_absen = {}
lock = threading.Lock()

WIB = timezone(timedelta(hours=7))


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/get_riwayat', methods=['GET'])
def get_riwayat():
    try:
        response = requests.get(GOOGLE_SHEET_URL, timeout=5)
        return jsonify(response.json())
    except Exception:
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
            'message': f'❌ Absen ditutup! Sekarang jam {waktu}.',
        })

    data = request.json.get('qr_data', '')
    data_split = data.split('|')

    if len(data_split) == 4:
        id_user, nama, kelas, role = data_split
        kunci_absen_hari_ini = f'{tanggal}|{id_user}'
        waktu_sekarang = time.time()

        with lock:
            # 1. JIKA SUDAH PERNAH DI-SCAN HARI INI
            if kunci_absen_hari_ini in sudah_absen:
                waktu_scan_terakhir = sudah_absen[kunci_absen_hari_ini]
                selisih_detik = waktu_sekarang - waktu_scan_terakhir

                # A. Jika scan susulan terjadi dalam rentang < 15 detik -> BLOKIR SPAM KILAT INSTAN!
                if selisih_detik < 15:
                    return jsonify({
                        'status': 'warning',
                        'message': f'⚠️ {nama} sudah absen hari ini!',
                    })

                # B. Jika sudah lewat > 15 detik -> Cek Google Sheet untuk memastikan
                masih_ada_di_sheet = False
                try:
                    res = requests.get(GOOGLE_SHEET_URL, timeout=4)
                    if res.status_code == 200:
                        riwayat = res.json()
                        masih_ada_di_sheet = any(
                            str(item.get('id')) == str(id_user)
                            and str(item.get('tanggal')) == tanggal
                            for item in riwayat
                            if isinstance(item, dict)
                        )
                except Exception:
                    masih_ada_di_sheet = True

                # Jika datanya masih ada di Sheet -> Tetap Tolak
                if masih_ada_di_sheet:
                    sudah_absen[kunci_absen_hari_ini] = waktu_sekarang
                    return jsonify({
                        'status': 'warning',
                        'message': f'⚠️ {nama} sudah absen hari ini!',
                    })
                else:
                    # Jika datanya SUDAH DIHAPUS manual dari Sheet -> Buka kunci
                    del sudah_absen[kunci_absen_hari_ini]

            # 2. PROSES ABSEN BARU
            sudah_absen[kunci_absen_hari_ini] = waktu_sekarang

        payload = {
            'id': id_user,
            'nama': nama,
            'kelas': kelas,
            'role': role,
            'tanggal': tanggal,
            'waktu': waktu,
        }

        try:
            requests.post(
                GOOGLE_SHEET_URL, json=payload, allow_redirects=True, timeout=5
            )
            return jsonify({
                'status': 'success',
                'message': f'✅ {nama} Berhasil Absen!',
                'siswa': payload,
            })
        except Exception as e:
            with lock:
                if kunci_absen_hari_ini in sudah_absen:
                    del sudah_absen[kunci_absen_hari_ini]
            return jsonify(
                {'status': 'error', 'message': f'⚠️ Gagal menyimpan: {str(e)}'}
            )
    else:
        return jsonify({'status': 'error', 'message': '⚠️ Format QR Code salah!'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
