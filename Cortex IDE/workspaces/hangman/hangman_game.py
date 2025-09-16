import random
from words import WORDS
from hangman_art import HANGMAN_ART

word = random.choice(WORDS)
display = ["_"] * len(word)
incorrect_guesses = 0

while True:
    print("".join(display))
    print(HANGMAN_ART[incorrect_guesses])
    guess = input("Guess a letter: ").lower()

    if guess in word:
        for i in range(len(word)):
            if word[i] == guess:
                display[i] = guess
    else:
        incorrect_guesses += 1

    if "_" not in display:
        print("You win!")
        break

    if incorrect_guesses == len(HANGMAN_ART):
        print("You lose! The word was", word)
        break
