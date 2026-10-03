"""Exact verified resource-boundary deltas; complete assemblies are never shipped."""

VARIANTS = (
    ('TazUO.dll', 'aac6afae48a00ddeef711238b5e84491ae4b9bd0aff89e91fb4fc956fc0b0b76', '71220e5b85f073695bd08d657670663e0b67031df28d2a02797370317edaf882', 'tazuo-5.2-cold-resource-client.patch.b64'),
    ('TazUO.dll', 'fe64075b3ec0ebbea7d07ffc8b4a010e53ba7767018491b6370026d86e7c3a80', '9b04d6e459904fea23c77e5f07cdec209b067c485588d02d0847cad1015f4f80', 'tazuo-5.2-cold-resource-client-render.patch.b64'),
    ('ClassicUO.Assets.dll', '1dd53cf0eea718aefeda33fba105c9797b138188be22562b47548c310524100d', '50adcf4e6e912a63d61a3fd8aa480f1bdfdbaa6abe473f6adee18ea09bb546f0', 'tazuo-5.2-cold-resource-assets.patch.b64'),
    ('ClassicUO.Assets.dll', '84340a487aeae33c0f17ae1b20a0c8d1b54122d1e23801e5a582452c7db905c9', '50060c31abd792c689c15df54a543ea01dbd171c827a38d68abb184577c89934', 'tazuo-5.2-cold-resource-assets-music.patch.b64'),
    ('ClassicUO.IO.dll', '334d1932f6fefe22731cccbbd812a6761d55ffa607ff0a4a291c2bc796c78483', 'bc7d5228849ae1699d239ceadb9fae4bd8142f9a6934d559a41bf51a9411ed24', 'tazuo-5.2-cold-resource-io.patch.b64'),
    ('ClassicUO.Renderer.dll', '1b0c7d0e7bcbf4f54e9d9c7f7229aa33d1ac84c9cdb40ebe4b45d2419676e906', 'c07d8c523884e9ca72f7d4d82f07c051ddac0831bc35f8175f8b1f69c1a1843f', 'tazuo-5.2-cold-resource-renderer.patch.b64'),
    ('FNA.dll', '18c88d506dbe15dcb4bb56f98e4b1756d9f8074ba8ab485ad36e10c087f168b1', '39d96e2bcacb5af9b5acfb0c0b62ee2f750a51e78a32aa0f7857e265fb38aa35', 'tazuo-5.2-cold-resource-fna.patch.b64'),
)

BACKUP_SUFFIX = '.before-memento-cold-resource-'


def backup_name(path, base):
    return path.with_name(path.name + BACKUP_SUFFIX + base[:12])
