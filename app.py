import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import pytz

# --- Timezone (Türkiye) ---
tz = pytz.timezone("Europe/Istanbul")

# --- Veritabanı Bağlantısı ---
conn = sqlite3.connect("personel.db", check_same_thread=False)
c = conn.cursor()

# Kullanıcı tablosu (admin onayı için approved sütunu eklendi)
c.execute("""CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT,
    role TEXT,
    approved INTEGER
)""")

# Log tablosu
c.execute("""CREATE TABLE IF NOT EXISTS logs (
    username TEXT,
    durum TEXT,
    giris TEXT,
    cikis TEXT,
    sure INTEGER
)""")
conn.commit()

# --- Admin hesabını otomatik ekle ---
c.execute("INSERT OR IGNORE INTO users (username, password, role, approved) VALUES (?, ?, ?, ?)",
          ("admin", "1234", "Yönetici", 1))
conn.commit()

# --- Sidebar Düzeni ---
st.sidebar.title("🔐 Kullanıcı Paneli")

# Giriş
st.sidebar.subheader("Giriş Yap")
username = st.sidebar.text_input("Kullanıcı Adı")
password = st.sidebar.text_input("Şifre", type="password")
login_btn = st.sidebar.button("Giriş")

# Kayıt Ol
st.sidebar.subheader("Kayıt Ol")
new_user = st.sidebar.text_input("Yeni Kullanıcı Adı")
new_pass = st.sidebar.text_input("Yeni Şifre", type="password")
if st.sidebar.button("Kayıt Ol"):
    try:
        c.execute("INSERT INTO users (username, password, role, approved) VALUES (?, ?, ?, ?)",
                  (new_user, new_pass, "Personel", 0))
        conn.commit()
        st.sidebar.success("Kullanıcı oluşturuldu ✅ (Admin onayı bekleniyor)")
    except:
        st.sidebar.error("Bu kullanıcı adı zaten mevcut ❌")

# Çıkış
if st.sidebar.button("Çıkış Yap"):
    st.session_state.clear()
    st.sidebar.success("Çıkış yapıldı ✅")

# Session kontrol
if "role" not in st.session_state:
    st.session_state.role = None
if "login_time" not in st.session_state:
    st.session_state.login_time = None

if login_btn:
    user = c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()
    if user:
        if user[3] == 1:  # approved
            st.session_state.role = user[2]
            st.session_state.user = user[0]
            st.session_state.login_time = datetime.now(tz)
            st.sidebar.success("Giriş başarılı ✅")
        else:
            st.sidebar.error("Hesabınız henüz admin tarafından onaylanmadı ❌")
    else:
        st.sidebar.error("Hatalı kullanıcı adı veya şifre ❌")

# Bildirim
if st.session_state.get("login_time"):
    elapsed = datetime.now(tz) - st.session_state.login_time
    if elapsed > timedelta(minutes=15):
        st.sidebar.warning("⏰ 15 dakika oldu, lütfen kontrol edin!")

# --- Personel Paneli ---
if st.session_state.get("role") == "Personel":
    st.title("👤 Personel Paneli")
    tab1, tab2, tab3 = st.tabs(["Durum Güncelle", "Şu An Dışarıda Olanlar", "Profilim"])

    with tab1:
        durum = st.selectbox("Durumunuz", ["İçeriye Gir", "Dışarıya Çık"])
        if st.button("Kaydet"):
            if durum == "İçeriye Gir":
                c.execute("INSERT INTO logs (username, durum, giris, cikis, sure) VALUES (?, ?, ?, ?, ?)", 
                          (st.session_state.user, "İçeride", datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"), None, None))
            else:
                c.execute("INSERT INTO logs (username, durum, giris, cikis, sure) VALUES (?, ?, ?, ?, ?)", 
                          (st.session_state.user, "Dışarıda", None, datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"), None))
            conn.commit()
            st.success("Durumunuz güncellendi ✅")

    with tab2:
        st_autorefresh(interval=10000, key="refresh")
        disaridaki = pd.read_sql("""
            SELECT username, cikis
            FROM logs
            WHERE durum='Dışarıda'
            ORDER BY cikis DESC
        """, conn)
        if not disaridaki.empty:
            for _, row in disaridaki.iterrows():
                st.info(f"🚶 {row['username']} şu anda dışarıda (çıkış: {row['cikis']})")
        else:
            st.success("Şu anda kimse dışarıda değil.")

    with tab3:
        profil = pd.read_sql("SELECT * FROM logs WHERE username=?", conn, params=(st.session_state.user,))
        if not profil.empty:
            st.dataframe(profil, use_container_width=True)
        else:
            st.info("Henüz log kaydınız yok.")

# --- Yönetici Paneli ---
elif st.session_state.get("role") == "Yönetici":
    st.title("👨‍💼 Yönetici Paneli")
    df = pd.read_sql("SELECT * FROM logs", conn)

    tab1, tab2, tab3 = st.tabs(["Dashboard", "Loglar", "Kullanıcı Onayı"])

    with tab1:
        toplam = df["username"].nunique()
        icerde = df[(df["durum"]=="İçeride")]["username"].nunique()
        disarda = df[(df["durum"]=="Dışarıda")]["username"].nunique()
        ort_sure = df["sure"].dropna().mean()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Personel", toplam)
        col2.metric("İçeride", icerde)
        col3.metric("Dışarıda (aktif)", disarda)
        col4.metric("Ortalama Süre (dk)", round(ort_sure,1) if not pd.isna(ort_sure) else 0)

    with tab2:
        st.dataframe(df, use_container_width=True)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Logs")
        excel_data = output.getvalue()
        st.download_button(
            label="📥 Excel Olarak İndir",
            data=excel_data,
            file_name="personel_logs.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    with tab3:
        pending = pd.read_sql("SELECT username FROM users WHERE approved=0", conn)
        if not pending.empty:
            st.warning("Onay bekleyen kullanıcılar:")
            for _, row in pending.iterrows():
                if st.button(f"Onayla: {row['username']}"):
                    c.execute("UPDATE users SET approved=1 WHERE username=?", (row['username'],))
                    conn.commit()
                    st.success(f"{row['username']} onaylandı ✅")
        else:
            st.success("Onay bekleyen kullanıcı yok.")

# --- Modern UI ---
st.sidebar.markdown("---")
st.sidebar.info("📱 Mobil ve masaüstü uyumlu modern arayüz")
