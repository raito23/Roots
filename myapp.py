from flask import Flask, request, render_template, session, redirect
from sklearn.metrics.pairwise import cosine_similarity
import hashlib
import numpy as np
from datetime import timedelta
import psycopg2
import psycopg2.extras
import spotipy
import os
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

load_dotenv(override=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Spotify APIの認証情報
client_id = os.getenv('CLIENT_ID')
client_secret = os.getenv('CLIENT_SECRET')

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id,
                                                           client_secret=client_secret),
                     language='ja')

# PostgreSQLへの接続情報
db_params = {
    'host': 'localhost',
    'dbname': os.getenv('DBNAME'),
    'user': os.getenv('USER'),
    'password': os.getenv('PASSWORD')
}

connection = psycopg2.connect(**db_params)

app.permanent_session_lifetime = timedelta(days=30)


#------------------------------------------------------------以下API関連------------------------------------------------------------
def get_top_tracks():#日本のトップ50を取得
    results = sp.user_playlist_tracks(user="spotify", playlist_id="37i9dQZEVXbKqiTGXuCOsB", limit=50, market="JP")
    return results['items']

def get_top_tracks_features():
    track_ids = [track["track"]["id"] for track in get_top_tracks()]
    features = sp.audio_features(track_ids)
    return features
#------------------------------------------------------------以下ページ関連------------------------------------------------------------
@app.before_request
def before_request():
    if not request.is_secure:
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url)
    
@app.route("/", methods=['GET', 'POST'])
@app.route('/mypage')
def mypage():
    if ("uid" in session and session["uid"] > 0 and "uname" in session and len(session["uname"]) > 0) or ("back_to_top" in request.args and request.args["back_to_top"] == "true"):
        uid = session["uid"]
        uname = session["uname"]
        return render_template("index.html", title="Route", uid=uid, uname=uname, top_tracks=get_top_tracks())
    else:
        return redirect("./login")
    
@app.route('/artist', methods=['GET', 'POST'])
def artist_page(): 
    artist_query = request.args.get('query_artist')
    song_query = request.args.get('query_song')
    
    if artist_query == "":
        return redirect("./")

    # アーティストの情報を取得
    results_search_artist = sp.search(q=artist_query, type="artist", limit=1, market="JP")
    artist_info = results_search_artist["artists"]["items"][0]
    artist_id = artist_info["id"]
    
    # アーティストのアルバム一覧を取得
    results_artist_albums = sp.artist_albums(artist_id, limit=15)
    albums = results_artist_albums['items']

    # アーティストの全トラックを取得
    all_tracks = []
    for album in albums:
        album_id = album['id']
        results_album_tracks = sp.album_tracks(album_id)
        all_tracks.extend(results_album_tracks['items'])
        
    song_info = None
    if song_query:
        for track in all_tracks:
            if song_query.lower() in track["name"].lower():
                song_info = track
                break
    if song_info is None:
        return redirect("./")
    song_features = sp.audio_features([song_info['id']])[0]
    song_feature_values = [
        song_features['danceability'],
        song_features['energy'],
        song_features['instrumentalness'],
        song_features['loudness'],
        song_features['speechiness'],
        song_features['valence']
    ]

    top_tracks_features = get_top_tracks_features()
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
    # コサイン類似度計算
    similarities = cosine_similarity([song_feature_values], features_matrix)
    # 類似度が高い順にソートして上位3曲のインデックスを取得
    top_similar_indices = similarities.argsort()[0][::-1][:5]

    # 上位5曲の情報を取得
    top_similar_tracks = [top_tracks_features[i] for i in top_similar_indices]
    return render_template("artist.html", title="Route", song_info=song_info, top_similar_tracks=top_similar_tracks)

# -----------------------------------------------------------以下ログイン関連------------------------------------------------------------
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