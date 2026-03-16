import pathlib
import json
import glob

import argostranslate.package
import argostranslate.translate


def download_and_install_package(from_code="en", to_code="es"):
    # Download and install Argos Translate package
    argostranslate.package.update_package_index()
    available_packages = argostranslate.package.get_available_packages()
    package_to_install = next(
        filter(
            lambda x: x.from_code == from_code and x.to_code == to_code, available_packages
        )
    )
    argostranslate.package.install_from_path(package_to_install.download())


def translate_sentence(sentence, from_code="en", to_code="es"):
    return argostranslate.translate.translate(sentence, from_code, to_code)


def translate_file(trans: dict, from_code="en", to_code="es")-> dict:
    """transelate english transcription json file in to spanish and save output json to <save_path>"""
    # transelate each sentence from en -> es 
    # while preserving attributes (start time, duration etc..)
    for segment in trans['segments']:
        segment['text'] = translate_sentence(segment['text'], from_code, to_code)

    # transelate text paragraph (without additional attributes)
    trans['text'] = translate_sentence(trans['text'], from_code, to_code)

    # set language to es
    trans['language'] = to_code

    return trans


def translate_all_files(source_directory, destination_directory, from_code="en", to_code="es"):
    """transelates all english Json transcription files in <source_directory
        to spanish Json files and saves them to <destination_directory>
        while keeping same file name and other attributes"""
    
    en_transcriptsion_directory = source_directory
    es_transcriptsion_directory = destination_directory

    # get a list of all json files in directory
    en_files = glob.glob(en_transcriptsion_directory + "/*.json")

    if not en_files:
        raise ValueError(f"no json files found in {source_directory}")

    # create destination driectory if it does not exist
    pathlib.Path(es_transcriptsion_directory).mkdir(parents=True, exist_ok=True)

    print(f"source_directory: {en_transcriptsion_directory}")
    print(f"destination_driectory {es_transcriptsion_directory}")
    print(f"Translating from {from_code} to {to_code}")
    print("")  # new line
    for file_path in en_files:
        save_path = str(pathlib.Path(es_transcriptsion_directory) / pathlib.Path(file_path).name)
        if pathlib.Path(save_path).exists():
            print(f"Skipping (already translated): {pathlib.Path(file_path).name}")
            continue
        print(f"Translating: {pathlib.Path(file_path).name}...", end="")

        with open(file_path, 'r') as file:
            en_trans = json.load(file)

        es_trans = translate_file(en_trans, from_code, to_code)

        with open(save_path, 'w') as outfile:
            outfile.write(json.dumps(en_trans))

        print("success!")

    return None


if __name__ == '__main__':
    from_code = 'en'
    to_code = 'es'
    source_directory = "./transcriptions_en"
    destination_directory = "./transcriptions_es"
    
    download_and_install_package(from_code, to_code)
    translate_all_files(source_directory, destination_directory)
