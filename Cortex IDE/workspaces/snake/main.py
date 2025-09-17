import menu

def main():
    while True:
        choice = menu.display_menu()
        if choice == '1':
            print("\033[1;32mStarting game...\033[0m")
            # Add game initialization code here
            break
        elif choice == '2':
            print("\033[1;31mExiting game.\033[0m")
            exit()
        else:
            print("\033[1;31mInvalid selection. Try again.\033[0m")