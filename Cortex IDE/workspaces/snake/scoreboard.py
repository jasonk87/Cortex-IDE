import turtle

class Scoreboard:
    def __init__(self):
        self.score = 0
        self.scoreboard = turtle.Turtle()
        self.scoreboard.speed(0)
        self.scoreboard.color("white")
        self.scoreboard.penup()
        self.scoreboard.hideturtle()
        self.scoreboard.goto(0, 260)
        self.scoreboard.write(f"Score: {self.score}", align="center", font=("Courier", 24, "normal"))

    def update_score(self, points):
        self.score += points
        self.scoreboard.clear()
        self.scoreboard.write(f"Score: {self.score}", align="center", font=("Courier", 24, "normal"))

    def reset(self):
        self.scoreboard.clear()
        self.scoreboard.write("Game Over", align="center", font=("Courier", 36, "normal"))
