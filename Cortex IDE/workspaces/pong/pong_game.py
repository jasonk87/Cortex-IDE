import pygame

game_over = False
score_player = 0
score_computer = 0

pygame.init()

# Screen dimensions
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pong Game")

# Clock for controlling frame rate
clock = pygame.time.Clock()


# Paddle class
class Paddle:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.width = 10
        self.height = 100
        self.velocity = 5

    def move_up(self):
        self.y -= self.velocity

    def move_down(self):
        self.y += self.velocity

    def draw(self):
        pygame.draw.rect(
            screen, (255, 255, 255), (self.x, self.y, self.width, self.height)
        )


# Ball class
class Ball:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.radius = 10
        self.velocity_x = 3
        self.velocity_y = 3

    def move(self):
        self.x += self.velocity_x
        self.y += self.velocity_y

    def draw(self):
        pygame.draw.circle(
            screen, (25, 25, 255), (int(self.x), int(self.y)), self.radius
        )


# Game objects
player_paddle = Paddle(650, HEIGHT // 2 - 50)
computer_paddle = Paddle(150, HEIGHT // 2 - 50)
ball = Ball(WIDTH // 2, HEIGHT // 2)

# Game loop
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # Player paddle movement
    keys = pygame.key.get_pressed()
    if keys[pygame.K_w] and player_paddle.y > 0:
        player_paddle.move_up()
    if keys[pygame.K_s] and player_paddle.y < HEIGHT - player_paddle.height:
        player_paddle.move_down()

    # Computer paddle AI
    if ball.y < computer_paddle.y + computer_paddle.height / 2:
        computer_paddle.move_up()
    elif ball.y > computer_paddle.y + computer_paddle.height / 2:
        computer_paddle.move_down()

    # Ball movement
    ball.move()

    # Ball collision with top/bottom
    if ball.y <= 0 or ball.y >= HEIGHT:
        ball.velocity_y *= -1

    # Ball collision with paddles
    if (
        ball.x - ball.radius <= player_paddle.x + player_paddle.width
        and player_paddle.y < ball.y < player_paddle.y + player_paddle.height
    ):
        ball.velocity_x *= -1
    if (
        ball.x + ball.radius >= computer_paddle.x
        and computer_paddle.y < ball.y < computer_paddle.y + computer_paddle.height
    ):
        ball.velocity_x *= -1

    # Scoring
    if ball.x < 0:
        score_computer += 1
        ball = Ball(WIDTH // 2, HEIGHT // 2)
        ball.velocity_x = 3
        ball.velocity_y = 3
    elif ball.x > WIDTH:
        score_player += 1
        ball = Ball(WIDTH // 2, HEIGHT // 2)
        ball.velocity_x = -3
        ball.velocity_y = 3

    # Draw everything
    screen.fill((0, 0, 0))
    player_paddle.draw()
    computer_paddle.draw()
    ball.draw()

    # Display scores
    font = pygame.font.SysFont("Arial", 30)
    score_text = font.render(
        f"Player: {score_player}  Computer: {score_computer}", True, (255, 255, 255)
    )
    screen.blit(score_text, (WIDTH // 2 - 150, 10))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
