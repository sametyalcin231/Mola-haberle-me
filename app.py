import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- Veritabanı Bağlantısı ---
conn = sqlite3.connect("personel.db", check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT,
    role TEXT
)""")
c.execute("""CREATE TABLE IF NOT EXISTS logs (
    username TEXT,
    durum TEXT,
    giris TEXT,
    cikis TEXT,
    sure INTEGER
)""")
conn.commit()

# --- Admin hesabını otomatik ekle ---
c.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", ("admin", "1234", "Yönetici"))
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
        c.execute("INSERT INTO users VALUES (?, ?, ?)", (new_user, new_pass, "Personel"))
        conn.commit()
        st.sidebar.success("Kullanıcı oluşturuldu ✅")
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
        st.session_state.role = user[2]
        st.session_state.user = user[0]
        st.session_state.login_time = datetime.now()
        st.sidebar.success("Giriş başarılı ✅")
    else:
        st.sidebar.error("Hatalı kullanıcı adı veya şifre ❌")

# Bildirim
if st.session_state.get("login_time"):
    elapsed = datetime.now() - st.session_state.login_time
    if elapsed > timedelta(minutes=15):
        st.sidebar.warning("⏰ 15 dakika oldu, lütfen kontrol edin!")

# --- Personel Paneli ---
if st.session_state.get("role") == "Personel":
    st.title("👤 Personel Paneli")
    tab1, tab2 = st.tabs(["Durum Güncelle", "Şu An Dışarıda Olanlar"])

    with tab1:
        durum = st.selectbox("Durumunuz", ["İçeriye Gir", "Dışarıya Çık"])
        if st.button("Kaydet"):
            if durum == "İçeriye Gir":
                # İçeriye giriş logu
                c.execute("INSERT INTO logs (username, durum, giris, cikis, sure) VALUES (?, ?, ?, ?, ?)", 
                          (st.session_state.user, "İçeride", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), None, None))
            else:
                # Dışarı çıkış logu anında yazılsın
                giris = c.execute("SELECT giris FROM logs WHERE username=? AND cikis IS NULL", (st.session_state.user,)).fetchone()
                if giris:
                    giris_time = datetime.strptime(giris[0], "%Y-%m-%d %H:%M:%S")
                    cikis_time = datetime.now()
                    sure = int((cikis_time - giris_time).total_seconds() / 60)
                    c.execute("UPDATE logs SET durum=?, cikis=?, sure=? WHERE username=? AND cikis IS NULL",
                              ("Dışarıda", cikis_time.strftime("%Y-%m-%d %H:%M:%S"), sure, st.session_state.user))
                else:
                    # Eğer giriş kaydı yoksa direkt dışarı logu aç
                    c.execute("INSERT INTO logs (username, durum, giris, cikis, sure) VALUES (?, ?, ?, ?, ?)",
                              (st.session_state.user, "Dışarıda", None, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0))
            conn.commit()

    with tab2:
        # sayfayı her 10 saniyede bir yenile
        st_autorefresh(interval=10000, key="refresh")

        # sadece şu anda dışarıda olanlar (cikis IS NULL)
        disaridaki = pd.read_sql("""
            SELECT username, giris
            FROM logs
            WHERE durum='Dışarıda' AND cikis IS NULL
        """, conn)
        if not disaridaki.empty:
            for _, row in disaridaki.iterrows():
                st.info(f"🚶 {row['username']} şu anda dışarıda (giriş: {row['giris']})")
        else:
            st.success("Şu anda kimse dışarıda değil.")

# --- Yönetici Paneli ---
elif st.session_state.get("role") == "Yönetici":
    st.title("👨‍💼 Yönetici Paneli")
    df = pd.read_sql("SELECT * FROM logs", conn)

    if not df.empty:
        tab1, tab2 = st.tabs(["Dashboard", "Loglar"])

        with tab1:
            toplam = df["username"].nunique()
            icerde = df[(df["durum"]=="İçeride") & (df["cikis"].isnull())]["username"].nunique()
            disarda = df[(df["durum"]=="Dışarıda") & (df["cikis"].isnull())]["username"].nunique()
            ort_sure = df["sure"].dropna().mean()

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Toplam Personel", toplam)
            col2.metric("İçeride", icerde)
            col3.metric("Dışarıda (aktif)", disarda)
            col4.metric("Ortalama Süre (dk)", round(ort_sure,1) if not pd.isna(ort_sure) else 0)

        with tab2:
            st.dataframe(df, use_container_width=True)

            # Excel export fix
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
    else:
        st.warning("Henüz kayıtlı log yok.")

# --- Modern UI ---
st.sidebar.markdown("---")
st.sidebar.info("📱 Mobil ve masaüstü uyumlu modern arayüz")
