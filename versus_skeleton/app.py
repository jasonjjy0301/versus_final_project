######################################
# VERSUS skeleton app.py
# CS460 Final Project
######################################
# Covers the core: register/login, create bracket, browse, view.
# Students extend with: predictions, voting, round-closing (stored
# procedure), triggers, leaderboard (window functions), recursive CTE,
# follows, comments, indexes.
###################################################

import flask
from flask import Flask, request, render_template, redirect, url_for
import mysql.connector
import flask_login
import datetime

app = Flask(__name__)
app.secret_key = 'super secret string'  # Change this!

# These will need to be changed according to your credentials.
DB_USER     = 'root'
DB_PASSWORD = 'your_password_here'
DB_NAME     = 'versus'
DB_HOST     = 'localhost'

def get_conn():
	return mysql.connector.connect(
		host=DB_HOST,
		user=DB_USER,
		password=DB_PASSWORD,
		database=DB_NAME,
		autocommit=False,
	)

conn = get_conn()


# begin code used for login
login_manager = flask_login.LoginManager()
login_manager.init_app(app)


def getUserList():
	cursor = conn.cursor()
	cursor.execute("SELECT username from Users")
	rows = cursor.fetchall()
	cursor.close()
	return rows


class User(flask_login.UserMixin):
	pass


@login_manager.user_loader
def user_loader(username):
	users = getUserList()
	if not(username) or username not in str(users):
		return
	user = User()
	user.id = username
	return user


@login_manager.request_loader
def request_loader(request):
	users = getUserList()
	username = request.form.get('username')
	if not(username) or username not in str(users):
		return
	user = User()
	user.id = username
	cursor = conn.cursor()
	cursor.execute("SELECT password FROM Users WHERE username = '{0}'".format(username))
	data = cursor.fetchall()
	cursor.close()
	pwd = str(data[0][0])
	user.is_authenticated = request.form['password'] == pwd
	return user


'''
A new page looks like this:
@app.route('new_page_name')
def new_page_function():
	return new_page_html
'''

@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'GET':
		return '''
			<form action='login' method='POST'>
				<input type='text' name='username' id='username' placeholder='username' />
				<input type='password' name='password' id='password' placeholder='password' />
				<input type='submit' name='submit' />
			</form><br />
			<a href='/'>Home</a>
		'''
	# The request method is POST (page is receiving data)
	username = request.form['username']
	cursor = conn.cursor()
	# check if username is registered
	cursor.execute("SELECT password FROM Users WHERE username = '{0}'".format(username))
	data = cursor.fetchall()
	cursor.close()
	if data:
		pwd = str(data[0][0])
		if request.form['password'] == pwd:
			user = User()
			user.id = username
			flask_login.login_user(user)
			return redirect(url_for('home'))
	# information did not match
	return "<a href='/login'>Try again</a><br />\
			<a href='/register'>or make an account</a>"


@login_manager.unauthorized_handler
def unauthorized_handler():
	return render_template('unauth.html')


# you can specify specific methods (GET/POST) in the function header instead
# of inside the function body
@app.route("/register", methods=['GET'])
def register():
	return render_template('register.html')


@app.route("/register", methods=['POST'])
def register_user():
	try:
		username = request.form.get('username')
		email    = request.form.get('email')
		password = request.form.get('password')
		bio      = request.form.get('bio')
	except:
		print("couldn't find all tokens")
		return redirect(url_for('register'))
	cursor = conn.cursor()
	if isUsernameUnique(username):
		cursor.execute(
			"INSERT INTO Users (username, email, password, bio) VALUES ('{0}', '{1}', '{2}', '{3}')".format(
				username, email, password, bio or ""))
		conn.commit()
		cursor.close()
		# log user in
		user = User()
		user.id = username
		flask_login.login_user(user)
		return render_template('hello.html', name=username, message='account created')
	else:
		cursor.close()
		print("username already in use")
		return redirect(url_for('register'))


def isUsernameUnique(username):
	# use this to check if a username has already been registered
	cursor = conn.cursor()
	cursor.execute("SELECT username FROM Users WHERE username = '{0}'".format(username))
	rows = cursor.fetchall()
	cursor.close()
	return len(rows) == 0


def getUserIdFromUsername(username):
	cursor = conn.cursor()
	cursor.execute("SELECT user_id FROM Users WHERE username = '{0}'".format(username))
	row = cursor.fetchone()
	cursor.close()
	return row[0] if row else None


def getUsernameFromUserId(uid):
	cursor = conn.cursor()
	cursor.execute("SELECT username FROM Users WHERE user_id = '{0}'".format(uid))
	row = cursor.fetchone()
	cursor.close()
	return row[0] if row else None

# end login code


# begin bracket creation code
@app.route('/create', methods=['GET', 'POST'])
@flask_login.login_required
def create_bracket():
	if request.method == 'POST':
		uid           = getUserIdFromUsername(flask_login.current_user.id)
		title         = request.form.get('title')
		description   = request.form.get('description')
		entrant_count = int(request.form.get('entrant_count'))
		cursor = conn.cursor()

		# 1. insert the bracket row
		cursor.execute(
			"INSERT INTO Brackets (host_id, title, description, entrant_count) VALUES ('{0}', '{1}', '{2}', '{3}')".format(
				uid, title, description or "", entrant_count))
		cursor.execute("SELECT LAST_INSERT_ID()")
		bracket_id = cursor.fetchone()[0]

		# 2. insert all entrants in seed order
		entrant_ids = []
		for seed in range(1, entrant_count + 1):
			entrant_name = request.form.get('entrant_' + str(seed))
			cursor.execute(
				"INSERT INTO Entrants (bracket_id, seed, name) VALUES ('{0}', '{1}', '{2}')".format(
					bracket_id, seed, entrant_name))
			cursor.execute("SELECT LAST_INSERT_ID()")
			entrant_ids.append(cursor.fetchone()[0])

		# 3. create Round 1 matchups (seed pairs: 1v2, 3v4, ...)
		round_1_slots = entrant_count // 2
		for slot in range(1, round_1_slots + 1):
			a = entrant_ids[(slot - 1) * 2]
			b = entrant_ids[(slot - 1) * 2 + 1]
			cursor.execute(
				"INSERT INTO Matchups (bracket_id, round, slot, entrant_a_id, entrant_b_id) VALUES ('{0}', 1, '{1}', '{2}', '{3}')".format(
					bracket_id, slot, a, b))

		# 4. create empty shells for later rounds
		slots = round_1_slots // 2
		round_num = 2
		while slots >= 1:
			for slot in range(1, slots + 1):
				cursor.execute(
					"INSERT INTO Matchups (bracket_id, round, slot) VALUES ('{0}', '{1}', '{2}')".format(
						bracket_id, round_num, slot))
			slots //= 2
			round_num += 1

		conn.commit()
		cursor.close()
		return redirect(url_for('view_bracket', bracket_id=bracket_id))
	else:
		return render_template('create.html')
# end bracket creation code

#start_round1
@app.route('/start_round1', methods=['POST'])
@flask_login.login_required
def start_round1():
	bracket_id = request.form.get('bracket_id')
	cursor = conn.cursor()
	cursor.execute(
		"UPDATE Brackets "
		"SET status = 'round_1' "
		"WHERE bracket_id = '{0}'".format(bracket_id))
	conn.commit()
	cursor.close()
	return redirect('/bracket{0}'.format(bracket_id))


#get round
def getRoundFromBracketId(bracket_id):
	cursor = conn.cursor()
	cursor.execute("SELECT status FROM Brackets WHERE bracket_id = '{0}'".format(bracket_id))
	row = cursor.fetchone()
	cursor.close()
	if not row:
		return None
	status = row[0]
	if status.startswith('round_'):
		return int(status.split('_')[1])
	return None

# begin close round code
@app.route('/close_round', methods=['POST'])
@flask_login.login_required
def close_round():
	bracket_id = request.form.get('bracket_id')
	b_round = getRoundFromBracketId(bracket_id)
	if b_round is None:
		return redirect('/bracket{0}'.format(bracket_id))
	cursor = conn.cursor()
	cursor.execute(
		"SELECT m.matchup_id, m.round, m.slot, m.entrant_a_id, m.entrant_b_id, m.votes_a, m.votes_b "
		"FROM Matchups m "
		"WHERE m.bracket_id = '{0}' AND m.round = '{1}'".format(bracket_id, b_round))
	row = cursor.fetchall()

	for m in row:
		matchup_id = m[0]
		slot = m[2]
		entrant_a_id = m[3]
		entrant_b_id = m[4]
		votes_a = m[5]
		votes_b = m[6]
		if votes_a > votes_b:
			winner = entrant_a_id
		else:
			winner = entrant_b_id
		cursor.execute(
			"UPDATE Matchups "
			"SET winner_entrant_id = '{0}' "
			"WHERE matchup_id = '{1}' AND round = '{2}'".format(
				winner, matchup_id, b_round))
		
		cursor.execute(
			"UPDATE Predictions "
			"SET correct = TRUE, points_earned = 1 "
			"WHERE matchup_id = '{0}' AND entrant_id = '{1}'".format(
				matchup_id, winner))
	
		cursor.execute(
			"UPDATE Predictions "
			"SET correct = FALSE, points_earned = 0 "
			"WHERE matchup_id = '{0}' AND entrant_id <> '{1}'".format(
				matchup_id, winner))
		
		if len(row) > 1:
			next_round = b_round+1
			next_slot = (slot+1)//2
			if slot % 2 == 1:
				cursor.execute(
					"UPDATE Matchups "
					"SET entrant_a_id = '{0}' "
					"WHERE bracket_id = '{1}' AND slot = '{2}' AND round = '{3}'".format(
					winner, bracket_id, next_slot, next_round))

			else:
				cursor.execute(
					"UPDATE Matchups "
					"SET entrant_b_id = '{0}' "
					"WHERE bracket_id = '{1}' AND slot = '{2}' AND round = '{3}'".format(
					winner, bracket_id, next_slot, next_round))
				
	if len(row) == 1:
		cursor.execute(
			"UPDATE Brackets "
			"SET status = 'completed' "
			"WHERE bracket_id = '{0}'".format(
			bracket_id)
		)
	else:
		next_status = 'round_{0}'.format(b_round + 1)
		cursor.execute(
			"UPDATE Brackets "
			"SET status = '{0}' "
			"WHERE bracket_id = '{1}'".format(
			next_status, bracket_id)
		)

	conn.commit()
	cursor.close()
	return redirect('/bracket{0}'.format(bracket_id))



		



# begin browse code
def getAllBrackets():
	cursor = conn.cursor()
	cursor.execute(
		"SELECT b.bracket_id, b.title, b.status, b.entrant_count, b.created_at, u.username "
		"FROM Brackets b JOIN Users u ON b.host_id = u.user_id "
		"ORDER BY b.created_at DESC")
	rows = cursor.fetchall()
	cursor.close()
	return rows


@app.route('/browse', methods=['GET'])
def browse():
	brackets = getAllBrackets()
	return render_template('browse.html', brackets=brackets)
# end browse code


# begin bracket view code
def getBracketInfo(bracket_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT b.bracket_id, b.title, b.description, b.status, b.entrant_count, u.username "
		"FROM Brackets b JOIN Users u ON b.host_id = u.user_id "
		"WHERE b.bracket_id = '{0}'".format(bracket_id))
	row = cursor.fetchone()
	cursor.close()
	return row


def getMatchupsForBracket(bracket_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT m.matchup_id, m.round, m.slot, ea.name, eb.name, ew.name, m.votes_a, m.votes_b, ea.entrant_id, eb.entrant_id "
		"FROM Matchups m "
		"LEFT JOIN Entrants ea ON ea.entrant_id = m.entrant_a_id "
		"LEFT JOIN Entrants eb ON eb.entrant_id = m.entrant_b_id "
		"LEFT JOIN Entrants ew ON ew.entrant_id = m.winner_entrant_id "
		"WHERE m.bracket_id = '{0}' "
		"ORDER BY m.round, m.slot".format(bracket_id))
	rows = cursor.fetchall()
	cursor.close()
	return rows


@app.route('/bracket<bracket_id>', methods=['GET'])
def view_bracket(bracket_id):
	bracket  = getBracketInfo(bracket_id)
	matchups = getMatchupsForBracket(bracket_id)
	comments = getCommentInfo(bracket_id)
	return render_template('bracket.html', bracket=bracket, matchups=matchups, comments=comments)
# end bracket view code


# begin prediction
@app.route('/predict', methods=['POST'])
@flask_login.login_required
def create_prediction():
	uid = getUserIdFromUsername(flask_login.current_user.id)
	matchup_id = request.form.get('matchup_id')
	entrant_id = request.form.get('entrant_id')
	bracket_id = request.form.get('bracket_id')
	cursor = conn.cursor()
	
	try:
		cursor.execute(
        	"INSERT INTO Predictions (user_id, matchup_id, entrant_id) "
        	"VALUES ('{0}', '{1}', '{2}')".format(uid, matchup_id, entrant_id)
    		)
		conn.commit()
	except:
		cursor.close()
		return redirect('/bracket{0}'.format(bracket_id))
    
	cursor.close()
	return redirect('/bracket{0}'.format(bracket_id))


# begin vote
@app.route('/vote', methods=['POST'])
@flask_login.login_required
def create_vote():
	uid = getUserIdFromUsername(flask_login.current_user.id)
	matchup_id = request.form.get('matchup_id')
	entrant_id = request.form.get('entrant_id')
	cursor = conn.cursor()
	cursor.execute(
		"SELECT m.entrant_a_id, m.entrant_b_id, m.bracket_id "
		"FROM Matchups m "
		"WHERE matchup_id = '{0}'".format(matchup_id) 
		)
	row = cursor.fetchone()
	entrant_a_id = row[0]
	entrant_b_id = row[1]
	bracket_id = row[2]

	try:
		cursor.execute(
			"INSERT INTO Votes (user_id, matchup_id, entrant_id) VALUES ('{0}', '{1}', '{2}')".format(
				uid, matchup_id, entrant_id)
        )
		if int(entrant_id) == int(entrant_a_id):
			cursor.execute(
				"UPDATE Matchups SET votes_a = votes_a+1 WHERE matchup_id = '{0}'".format(
				matchup_id)
			)
		elif int(entrant_id) == int(entrant_b_id):
			cursor.execute(
				"UPDATE Matchups SET votes_b = votes_b+1 WHERE matchup_id = '{0}'".format(
				matchup_id)
			)
		conn.commit()
	except:
		cursor.close()
		return redirect('/bracket{0}'.format(bracket_id))

	cursor.close()
	return redirect('/bracket{0}'.format(bracket_id))







#begin profile view code
#get userinfo for profile
def getUserInfo(user_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT user_id, username, email, bio, created_at "
		"FROM Users u "
		"WHERE user_id = '{0}'".format(user_id))
	row = cursor.fetchone()
	cursor.close()
	return row

#get achieveinfo for profile
def getAchievementinfo(user_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT a.A_code, a.A_name,  u1.awarded_at "
		"FROM Users u JOIN User_Achievements u1 ON u.user_id = u1.user_id "
		"JOIN Achievements a ON u1.A_code = a.A_code "
		"WHERE u.user_id = '{0}'".format(user_id))
	rows = cursor.fetchall()
	cursor.close()
	return rows

#get getUserNumber_of_predictions_made
def getUserNumber_of_predictions_made(user_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT COUNT(*) "
		"FROM Users u JOIN Predictions p ON p.user_id = u.user_id "
		"WHERE u.user_id = '{0}'".format(user_id))
	row = cursor.fetchone()
	cursor.close()
	return row

#get getUsertotal prediction points across all brackets, 
def getUserrPredictionPointsAcrossAllBrackets(user_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT SUM(points_earned) "
		"FROM Users u JOIN Predictions p ON p.user_id = u.user_id "
		"WHERE u.user_id = '{0}' ".format(user_id))
	row = cursor.fetchone()
	cursor.close()
	return row

#getUserrNumber_of_correct_picks
def getUserrNumber_of_correct_picks(user_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT COUNT(*) "
		"FROM Users u JOIN Predictions p ON p.user_id = u.user_id "
		"WHERE u.user_id = '{0}' AND p.correct = TRUE".format(user_id))
	row = cursor.fetchone()
	cursor.close()
	return row

#brackets they have hosted, 
def getUserbrackets_the_have_hosted(user_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT bracket_id, title "
		"FROM Brackets "
		"WHERE host_id= '{0}'" .format(user_id))
	rows = cursor.fetchall()
	cursor.close()
	return rows

#followed
def getUserfollowing(user_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT u.user_id, u.username "
		"FROM Follow f JOIN Users u ON f.followed_id = u.user_id "
		"WHERE f.follower_id= '{0}'" .format(user_id))
	rows = cursor.fetchall()
	cursor.close()
	return rows

#follower
def getUserfollower(user_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT u.user_id, u.username "
		"FROM Follow f JOIN Users u ON f.follower_id = u.user_id "
		"WHERE f.followed_id= '{0}'".format(user_id))
	rows = cursor.fetchall()
	cursor.close()
	return rows


@app.route('/profile', methods=['GET'])
@flask_login.login_required
def view_profile():
	uid = getUserIdFromUsername(flask_login.current_user.id)
	user = getUserInfo(uid)
	achievements = getAchievementinfo(uid)
	prediction_count = getUserNumber_of_predictions_made(uid)
	points = getUserrPredictionPointsAcrossAllBrackets(uid)
	correct = getUserrNumber_of_correct_picks(uid)
	hosted = getUserbrackets_the_have_hosted(uid)
	followers = getUserfollower(uid)
	following = getUserfollowing(uid)
	return render_template('profile.html', user= user, achievements=achievements, prediction_count= 
						prediction_count, points=points, correct=correct,hosted =hosted, followers=followers,following =following )
# end profile view code







#begin comments
def getCommentInfo(bracket_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT c.comment_id, c.user_id, c.matchup_id, c.body, c.created_at, u.user_id, u.username "
		"FROM Comments c "
		"JOIN Users u ON c.user_id = u.user_id "
		"JOIN Matchups m ON m.matchup_id = c.matchup_id "
		"WHERE  m.bracket_id ='{0}' "
        "ORDER BY c.created_at".format(bracket_id) 
		)
	row = cursor.fetchall()
	cursor.close()
	return row
	
def getBracketID(matchup_id):
	cursor = conn.cursor()
	cursor.execute("SELECT bracket_id FROM Matchups WHERE matchup_id = '{0}'".format(matchup_id))
	row = cursor.fetchone()
	cursor.close()
	return row[0]


#write comments
@app.route('/comments', methods=['POST'])
@flask_login.login_required
def create_comment():
	uid = getUserIdFromUsername(flask_login.current_user.id)
	matchup_id = request.form.get('matchup_id')
	bracket_id = getBracketID(matchup_id)
	body = request.form.get('comments')
	cursor = conn.cursor()
	try:
		cursor.execute(
				"INSERT INTO Comments (user_id, matchup_id, body) VALUES ('{0}', '{1}', '{2}')".format(
					uid, matchup_id, body))
		conn.commit()
	except:
		cursor.close()
		return redirect('/bracket{0}'.format(bracket_id))
	cursor.close()
	return redirect('/bracket{0}'.format(bracket_id))


@app.route('/follow', methods=['POST'])
@flask_login.login_required
def follow():
	follower_id = getUserIdFromUsername(flask_login.current_user.id)
	followed_id = request.form.get('followed_id')
	matchup_id = request.form.get('matchup_id')
	bracket_id = getBracketID(matchup_id)
	cursor = conn.cursor()
	try:
		cursor.execute(
			"INSERT INTO Follow (follower_id, followed_id) VALUES ('{0}', '{1}')".format(
					follower_id, followed_id))
		conn.commit()
	except:
		cursor.close()
		return redirect('/bracket{0}'.format(bracket_id))
	cursor.close()
	return redirect('/bracket{0}'.format(bracket_id))

#Leaderboard
def getLeaderboard():
	cursor = conn.cursor()
	cursor.execute(
		"SELECT u.user_id, u.username, COALESCE(SUM(p.points_earned),0), "
		"RANK() OVER (ORDER BY COALESCE(SUM(p.points_earned), 0) DESC) AS r, "
		"DENSE_RANK()  OVER (ORDER BY COALESCE(SUM(p.points_earned), 0) DESC) AS dense_r,"
		"PERCENT_RANK() OVER (ORDER BY COALESCE(SUM(p.points_earned), 0) DESC) AS percent_r "
		"FROM  Users u "
		"LEFT JOIN Predictions p ON p.user_id = u.user_id "
		"GROUP BY u.user_id "
		"ORDER BY COALESCE(SUM(p.points_earned),0) DESC "
	)
	rows = cursor.fetchall()
	cursor.close()
	return rows

@app.route('/leaderboard', methods=['GET'])
def view_Leaderboard():
	leaderboard = getLeaderboard()
	return render_template('leaderboard.html', leaderboard=leaderboard)
#END Leaderboard


def getChampionPath(bracket_id):
	cursor = conn.cursor()
	cursor.execute(
		"WITH RECURSIVE ChampionPath AS ("
		"SELECT m.matchup_id, m.bracket_id, m.round, m.slot, m.entrant_a_id, m.entrant_b_id, m.winner_entrant_id, m.votes_a, m.votes_b "
		"FROM Matchups m "
		"WHERE m.round = (SELECT MAX(round) FROM Matchups WHERE bracket_id = '{0}') " 
		"AND m.bracket_id = '{0}' " 
			" UNION ALL "
		"SELECT m.matchup_id, m.bracket_id, m.round, m.slot, m.entrant_a_id, m.entrant_b_id, m.winner_entrant_id, m.votes_a, m.votes_b "
		"FROM Matchups m "
		"JOIN ChampionPath c ON m.round = c.round-1 AND m.winner_entrant_id = c.winner_entrant_id AND m.bracket_id = c.bracket_id "
		")"
		" SELECT c.matchup_id, c.bracket_id, c.round, c.slot, c.votes_a, c.votes_b, ea.name, eb.name, e.name " 
		"FROM ChampionPath c " 
		"JOIN Entrants ea ON c.entrant_a_id = ea.entrant_id "
		"JOIN Entrants eb ON c.entrant_b_id = eb.entrant_id "
		"JOIN Entrants e ON c.winner_entrant_id = e.entrant_id "
		"ORDER BY c.round".format(bracket_id)
	)
	rows = cursor.fetchall()
	cursor.close()
	return rows


@app.route('/champion_path', methods=['POST'] )
def champion_path():
	bracket_id = request.form.get('bracket_id')
	championpath = getChampionPath(bracket_id)
	return render_template('champion_path.html',championpath=championpath)


# default page
@app.route('/', methods=['GET', 'POST'])
def home():
	if request.method == 'POST':
		flask_login.logout_user()
	try:
		username = flask_login.current_user.id
		return render_template('hello.html', name=username, message='welcome to VERSUS')
	except AttributeError:  # not logged in
		return render_template('hello.html', message=None)


if __name__ == "__main__":
	# this is invoked when in the shell you run
	# $ python app.py
	app.debug = True
	app.run(port=5000, debug=True)
