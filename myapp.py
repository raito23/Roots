from flask import Flask, request, render_template, session, redirect
from sklearn.metrics.pairwise import cosine_similarity
import hashlib
import numpy as np
from datetime import timedelta
import spotipy
import os
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
from flask import Flask
from pymongo import MongoClient
load_dotenv(override=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = MongoClient(os.getenv('SECRET_KEY'))
client_id     = MongoClient(os.getenv('CLIENT_ID'))
client_secret = MongoClient(os.getenv('CLIENT_SECRET'))

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id,
                                                           client_secret=client_secret),
                                                           language='ja')

# connection = psycopg2.connect("host=localhost \
# dbname=MongoClient(os.getenv('DBNAME')) user=MongoClient(os.getenv('USER')) password=MongoClient(os.getenv('PASSWORD'))")

app.permanent_session_lifetime = timedelta(days=30)

#------------------------------------------------------------以下API関連------------------------------------------------------------
def get_top_tracks():#日本のトップ30を取得
    results = sp.user_playlist_tracks(user="spotify", playlist_id="37i9dQZEVXbKqiTGXuCOsB", limit=30, market="JP")
    return results['items']

def get_top_tracks_features():#日本のトップ30の特徴量を取得
    track_ids = [track["track"]["id"] for track in get_top_tracks()]
    features = sp.audio_features(track_ids)
    return features
top_tracks_features = get_top_tracks_features()

print("コサイン類似度行列:")
cleaned_features = [
    {
        'danceability': track['danceability'],
        'energy': track['energy'],
        'instrumentalness': track['instrumentalness'],
        'loudness': track['loudness'],
        'speechiness': track['speechiness'],
        'valence': track['valence']
    }
    for track in top_tracks_features
    if 'audio_features' in track.get('type', '')
]
features_matrix = np.array([list(track.values()) for track in cleaned_features])
print(features_matrix)

# cosine_similarities = cosine_similarity(features_matrix, features_matrix)
# print(cosine_similarities)


#------------------------------------------------------------以下ページ関連------------------------------------------------------------
@app.before_request
def before_request():
    if not request.is_secure:
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url)
    
@app.route("/", methods=['GET', 'POST'])
@app.route('/mypage')
def mypage(): #マイページ
    if ("uid" in session and session["uid"] > 0 and "uname" in session and len(session["uname"]) > 0) or ("back_to_top" in request.args and request.args["back_to_top"] == "true"):
        uid = session["uid"]
        uname = session["uname"]
        return render_template("index.html", title="Route", uid=uid, uname=uname, top_tracks=get_top_tracks())
    else:
        return redirect("./login")
    
@app.route('/artist', methods=['GET', 'POST'])
def artist_page(): #アーティスト検索ページ
    artist_query = request.args.get('query')
    if artist_query == "":
        return redirect("./")
    else:
        results_search = sp.search(q=artist_query, type="artist", limit=1, market="JP")
        artist_info = results_search["artists"]["items"][0]
        artist_id = artist_info["id"]
        artist_name = artist_info["name"]
        artist_image = artist_info["images"][0]["url"] if artist_info.get("images") else ""
        results_artist_albums = sp.artist_albums(artist_id, limit=10)
        album_list = [album for album in results_artist_albums["items"]]
        return render_template("artist.html", title="アーティストページ", artist_name=artist_name, artist_image=artist_image, albums=album_list)
    
#------------------------------------------------------------以下認証関連------------------------------------------------------------
@app.route('/login', methods=['GET'])
def login():
    error_message = session.get('error_message')
    session.pop('error_message', None)
    return render_template("login.html", title="Roots", error_message=error_message)
@app.route('/regist', methods=['GET'])
def regist():
    return render_template("regist.html", title="regist form")

@app.route('/logingin', methods=['POST'])
def logingin():
    error_message = None
    if request.method == 'POST' and "emf" in request.form and "pwf" in request.form and len(request.form['emf']) > 0 and len(request.form['pwf']) > 0:
        emf = request.form['emf']
        pwf = request.form['pwf']
        cur = connection.cursor()
        cur.execute("SELECT COUNT(uid) FROM flaskauth WHERE email = %s;", (emf,))
        res = cur.fetchone()
        cur.close()
        if res[0] > 0:
            cur = connection.cursor()
            cur.execute("SELECT uid, pw, uname FROM flaskauth WHERE email = %s;", (emf,))
            res = cur.fetchone()
            cur.close()
            cpw = hashlib.sha512(pwf.encode("utf-8")).hexdigest()
            if cpw == res[1]:
                session["uid"] = res[0]
                session["uname"] = res[2]
                return redirect("./")
            else:
                error_message = "パスワードが間違っています。"
                session['error_message'] = error_message
                return redirect("./login")
        else:
            error_message = "このアドレスは登録されていません。"
            session['error_message'] = error_message
            return redirect("./login")
    else:
        error_message = "フォームはすべて必須項目です."
        session['error_message'] = error_message
        return redirect("./login")

@app.route('/registing', methods=['POST'])
def registing():
    msg = []
    aflag = 0
    if request.method == 'POST' and "unf" in request.form and "emf" in request.form and "pwf1" in request.form and "pwf2" in request.form and len(request.form['unf']) > 0 and len(request.form['emf']) > 0 and len(request.form['pwf1']) > 0 and len(request.form['pwf2']) > 0:
        unf = request.form['unf']
        emf = request.form['emf']
        pwf1 = request.form['pwf1']
        pwf2 = request.form['pwf2']
        cur = connection.cursor()
        cur.execute("SELECT COUNT(uid) FROM flaskauth WHERE email = %s;", (emf,))
        res = cur.fetchone()
        cur.close()
        if res[0] > 0:
            msg.append("このアドレスは既に登録されています。")
        elif pwf1 != pwf2:
            msg.append("パスワードが一致しませんでした。")
        else:
            cur = connection.cursor()
            epw = hashlib.sha512(pwf1.encode("utf-8")).hexdigest()
            cur.execute("INSERT INTO flaskauth (uname, email, pw) VALUES (%s, %s, %s);", (unf, emf, epw))
            connection.commit()
            cur.close()
            msg.append("登録完了しました。")
            aflag = 1
    else:
        msg.append("フォームはすべて必須項目です.")
    return render_template("registing.html", title="registing an user", message=msg, aflag=aflag)

@app.route('/logout')
def logout():
    session.pop("uid", None)
    session.pop("uname", None)
    return redirect("./")


if __name__ == "__main__":
    app.run(ssl_context='adhoc')