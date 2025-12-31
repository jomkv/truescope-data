import hashlib


def generate_doc_id(url: str) -> str:
    # Encode the url to bytes
    encoded_url = url.encode("utf-8")

    # Create a SHA256 hash object and update it with the encoded url
    hash_url = hashlib.sha256(encoded_url)

    # Get the hash in hexadecimal format (a 64-character string)
    return hash_url.hexdigest()
