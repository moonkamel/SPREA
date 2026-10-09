from api.address import address_key, same_address, same_street


def test_same_address_across_sources():
    assert same_address("32 Rue Jean Bart (Saint-Pol-sur-Mer) 59430 Dunkerque", "32 Rue Jean Bart St Pol 59430 Dunkerque")
    assert same_address("13 Rue Vincent d’Indy 59650 Villeneuve-d'Ascq", "13 Rue Vincent dâ€™Indy 59650 Villeneuve-d'Ascq")
    assert same_address("195 Rue de la République 59430 Dunkerque", "195 Rue de la RÃ©publique 59430 Dunkerque")
    assert same_address("18bis Rue Edmond Bricout 59540 Caudry", "18 BIS RUE EDMOND BRICOUT 59540 CAUDRY")
    assert same_address("2BIS Rue Gauthier de Chatillon 59000 Lille", "2b Rue Gauthier de Châtillon 59000 Lille")
    assert same_address("104BIS Rue Boucher de Perthes 59800 Lille", "104b Rue Boucher de Perthes 59800 Lille")
    assert not same_address("104 Rue Boucher de Perthes 59800 Lille", "104b Rue Boucher de Perthes 59800 Lille")
    assert same_address("2 Chemin des Grands Bas 25000 Besançon", "2 che des grands bas 25000 Besançon")
    # Next door, or another street
    assert not same_address("18 Rue Edmond Bricout 59540 Caudry", "18bis Rue Edmond Bricout 59540 Caudry")
    assert not same_address("69 Rue Boucher de Perthes 59800 Lille", "75 Rue Boucher de Perthes 59800 Lille")
    assert not same_address("10 Rue de Paris 59000 Lille", "10 Rue de Paris 59800 Lille")
    assert not same_street("68 rue de Vesoul 25000 Besançon", "2 che des grands bas 25000 Besançon")
    assert not same_address("", "") and address_key(None) == ""
