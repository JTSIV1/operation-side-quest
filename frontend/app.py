from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/results")
def results():
    return render_template("results.html")

@app.route("/friends")
def friends():
    return render_template("friends.html")

@app.route("/saved-routes")
def saved_routes():
    return render_template("saved_routes.html")

@app.route("/account")
def account():
    return render_template("account.html")
  
@app.route("/leaderboard")
def leaderboard():
    return render_template("leaderboard.html")

if __name__ == "__main__":
    app.run(debug=True)
