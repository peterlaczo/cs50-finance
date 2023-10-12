import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Get cash balance from db
    rows = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    if not rows:
        session.clear()
        return apology("Please login again", 401)
    cash = rows[0]["cash"]

    # Initialize total
    total = cash

    # Get holdings from db
    holdings = db.execute(
        "SELECT symbol, SUM(shares) AS total_shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING total_shares > 0",
        session["user_id"],
    )

    # Fetch information for each holding
    for holding in holdings:
        # Quote each symbol for current price
        quote = lookup(holding["symbol"])

        # Ensure symbol was found
        if not quote:
            return apology(f"invalid symbol '{holding['symbol']}'", 400)

        # Store holding name and current unit price
        holding["name"] = quote["name"]
        holding["unit_price"] = quote["price"]

        # Calculate total price
        holding["total_price"] = holding["unit_price"] * holding["total_shares"]

        # Update total
        total += holding["total_price"]

    return render_template("index.html", holdings=holdings, cash=cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure symbol is provided
        if not request.form.get("symbol"):
            return apology("must provide a symbol", 400)

        # Ensure number of shares is a positive integer
        if not request.form.get("shares"):
            return apology("must provide number of shares", 400)
        try:
            shares = int(request.form.get("shares"))
            if shares < 1:
                raise ValueError()
        except ValueError:
            return apology("number of shares must be a positive integer", 400)

        # Lookup symbol via API
        quote = lookup(request.form.get("symbol"))

        # Ensure symbol was found
        if not quote:
            return apology("invalid symbol", 400)

        # Get valid symbol and current price
        symbol = quote["symbol"]
        price = quote["price"]

        # Calculate buying price
        buying_price = shares * price

        # Get user's cash balance
        rows = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        if not rows:
            session.clear()
            return apology("Please login again", 401)
        cash = rows[0]["cash"]

        # Ensure user can afford the selected shares
        if cash < buying_price:
            return apology("your balance is too low", 400)

        # Reduce cash balance with buying price
        cash_out = db.execute(
            "UPDATE users SET cash = cash - ? WHERE id = ?",
            buying_price,
            session["user_id"],
        )
        if not cash_out:
            return apology("Something went wrong during cash withdrawal", 400)

        # Complete transaction
        transaction = db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, unit_price) VALUES(?, ?, ?, ?)",
            session["user_id"],
            symbol,
            shares,
            price,
        )
        if not transaction:
            return apology("Something went wrong during transaction", 400)

        # Give feedback
        flash(
            f"Successfully bought {shares} share(s) of {symbol} for {usd(buying_price)}!"
        )

        # Redirect to portfolio
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Get history for current user
    transaction_history = db.execute(
        "SELECT timestamp, symbol, shares, unit_price, ABS(unit_price * shares) AS total_price FROM transactions WHERE user_id = ?",
        session["user_id"],
    )

    return render_template("history.html", transaction_history=transaction_history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide a symbol", 400)

        # Lookup quote for symbol via API
        quote = lookup(request.form.get("symbol"))

        # Ensure result was found
        if not quote:
            return apology("invalid symbol", 400)

        # Render results
        return render_template("quote.html", quote=quote)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure username does not exist already
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )
        if rows:
            return apology("username already exists", 400)

        # Ensure password and confirmation were submitted and match
        if not request.form.get("password") or not request.form.get("confirmation"):
            return apology("must provide password two times", 400)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        # Add new user to database
        new_user = db.execute(
            "INSERT INTO users (username, hash) VALUES (?, ?)",
            request.form.get("username"),
            generate_password_hash(request.form.get("password")),
        )
        if not new_user:
            return apology("something went wrong", 400)
        else:
            # Remember which user has registered
            session["user_id"] = new_user

        # Show flash message
        flash("Registered successfully")

        # Redirect to root
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure symbol is provided
        if not request.form.get("symbol"):
            return apology("must provide a symbol", 400)

        # Ensure number of shares is a positive integer
        if not request.form.get("shares"):
            return apology("must provide number of shares", 400)
        try:
            shares = int(request.form.get("shares"))
            if shares < 1:
                raise ValueError()
        except ValueError:
            return apology("number of shares must be a positive integer", 400)

        # Ensure selected symbol is available
        holdings = db.execute(
            "SELECT symbol, SUM(shares) AS shares_available FROM transactions WHERE user_id = ? AND symbol = ? GROUP BY symbol HAVING shares_available > 0",
            session["user_id"],
            request.form.get("symbol"),
        )
        if not holdings:
            return apology("symbol is not owned", 400)
        holding = holdings[0]

        # Ensure user has enough shares to sell
        if shares > holding["shares_available"]:
            return apology("too many shares", 400)

        # Lookup symbol via API for current price
        quote = lookup(request.form.get("symbol"))

        # Ensure symbol was found online (unlikely, but be safe)
        if not quote:
            return apology("ERROR: invalid symbol is owned", 400)
        symbol = quote["symbol"]
        price = quote["price"]

        # Calculate selling price
        selling_price = shares * price

        # Complete sell transaction
        transaction = db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, unit_price) VALUES(?, ?, ?, ?)",
            session["user_id"],
            symbol,
            shares * (-1),
            price,
        )
        if not transaction:
            return apology("Something went wrong during transaction", 400)

        # Add selling price to cash balance
        cash_in = db.execute(
            "UPDATE users SET cash = cash + ? WHERE id = ?",
            selling_price,
            session["user_id"],
        )
        if not cash_in:
            return apology("Something went wrong during cash deposit", 400)

        # Give feedback
        flash(
            f"Successfully sold {shares} share(s) of {symbol} for {usd(selling_price)}!"
        )

        # Redirect to portfolio
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        # Get holdings from db
        holdings = db.execute(
            "SELECT symbol FROM transactions WHERE user_id = ? GROUP BY symbol HAVING SUM(shares) > 0",
            session["user_id"],
        )

        # Create a list of available symbols
        symbols = [holding["symbol"] for holding in holdings]

        # Render template with available symbols
        return render_template("sell.html", symbols=symbols)
