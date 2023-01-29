from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, FloatField, SubmitField, SelectField
from wtforms.validators import DataRequired


class LoginForm(FlaskForm):
    challenge = PasswordField("Challenge", render_kw={"autofocus": True})
    submit = SubmitField("Submit")


class RegisterForm(FlaskForm):
    submit = SubmitField("Generate")


class TickerForm(FlaskForm):
    description = StringField(
        "Description", validators=[DataRequired()], render_kw={"autofocus": True}
    )
    token = StringField("Token", validators=[DataRequired()])
    price = FloatField("Price", validators=[DataRequired()])
    currency = SelectField(
        "Currency",
        validators=[DataRequired()],
        choices=[("eur", "eur"), ("usd", "usd"), ("aud", "aud")],
    )
    submit = SubmitField("Create")


class AssetForm(FlaskForm):
    ticker = SelectField("Ticker", validators=[DataRequired()])
    shares = FloatField("Shares", validators=[DataRequired()])
    target = FloatField("Target", validators=[DataRequired()])
    sector = SelectField(
        "Sector",
        validators=[DataRequired()],
        choices=[
            ("stocks", "stocks"),
            ("crypto", "crypto"),
            ("cash", "cash")
        ],
    )
    submit = SubmitField("Create")