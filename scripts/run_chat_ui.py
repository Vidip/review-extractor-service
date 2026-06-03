from src.chat.gradio_app import main, parse_args

if __name__ == "__main__":
    main(port=parse_args().port)
