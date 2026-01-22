-- SPREA Database Schema
-- Optimized for 3CL-2021 Energy Simulation
-- Geographic support via PostGIS

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";

-- Custom Types (ENUMs)
CREATE TYPE user_role AS ENUM ('user', 'admin', 'professional');
CREATE TYPE subscription_tier AS ENUM ('free', 'premium', 'enterprise');
CREATE TYPE climate_zone AS ENUM ('H1a', 'H1b', 'H1c', 'H2a', 'H2b', 'H2c', 'H2d', 'H3');
CREATE TYPE dpe_class AS ENUM ('A', 'B', 'C', 'D', 'E', 'F', 'G');
CREATE TYPE orientation_type AS ENUM ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW');

-- Tables

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    role user_role NOT NULL DEFAULT 'user',
    company_name TEXT,
    subscription_tier subscription_tier NOT NULL DEFAULT 'free',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE properties (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    address TEXT NOT NULL,
    ademe_dpe_number CHAR(13),
    construction_year INTEGER,
    shab FLOAT NOT NULL, -- Surface habitable
    altitude FLOAT,
    climate_zone climate_zone,
    dpe_class_current dpe_class,
    ges_class_current dpe_class,
    coordinates GEOMETRY(Point, 4326),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Comments for properties
COMMENT ON COLUMN properties.shab IS 'Surface habitable en m²';
COMMENT ON COLUMN properties.altitude IS 'Altitude du bâtiment en mètres';
COMMENT ON COLUMN properties.ademe_dpe_number IS 'Numéro d''enregistrement DPE ADEME (13 caractères)';

CREATE TABLE walls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    surface FLOAT NOT NULL,
    u_value FLOAT, -- Coefficient de transmission thermique
    resistance FLOAT, -- Résistance thermique
    orientation orientation_type,
    insulation_type TEXT,
    material TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Comments for walls
COMMENT ON COLUMN walls.surface IS 'Surface de la paroi en m²';
COMMENT ON COLUMN walls.u_value IS 'Coefficient de transmission thermique en W/m².K';
COMMENT ON COLUMN walls.resistance IS 'Résistance thermique en m².K/W';

CREATE TABLE windows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    surface FLOAT NOT NULL,
    u_value FLOAT,
    glazing_type TEXT,
    solar_factor_sw FLOAT,
    has_shutters BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Comments for windows
COMMENT ON COLUMN windows.surface IS 'Surface de la fenêtre en m²';
COMMENT ON COLUMN windows.u_value IS 'Coefficient de transmission thermique en W/m².K';
COMMENT ON COLUMN windows.solar_factor_sw IS 'Facteur solaire Sw (sans unité, entre 0 et 1)';

CREATE TABLE systems (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    system_type TEXT NOT NULL, -- ex: chauffage, ECS, ventilation
    energy_source TEXT, -- ex: électricité, gaz, bois
    efficiency_etas FLOAT, -- Efficacité énergétique saisonnière
    generation_year INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Comments for systems
COMMENT ON COLUMN systems.efficiency_etas IS 'Efficacité énergétique saisonnière (Etas) en %';

CREATE TABLE simulations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    target_class dpe_class,
    estimated_cost FLOAT,
    new_consumption_kwh FLOAT,
    new_dpe_class dpe_class,
    roi_years FLOAT,
    selected_works JSONB, -- Liste des travaux sélectionnés et leurs impacts
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Comments for simulations
COMMENT ON COLUMN simulations.estimated_cost IS 'Coût estimé des travaux en Euros (€)';
COMMENT ON COLUMN simulations.new_consumption_kwh IS 'Nouvelle consommation estimée en kWh/m².an';
COMMENT ON COLUMN simulations.roi_years IS 'Retour sur investissement en années';

-- Indexes
CREATE INDEX idx_properties_ademe_num ON properties(ademe_dpe_number);
CREATE INDEX idx_properties_user_id ON properties(user_id);
CREATE INDEX idx_properties_coords ON properties USING GIST (coordinates);
CREATE INDEX idx_walls_property_id ON walls(property_id);
CREATE INDEX idx_windows_property_id ON windows(property_id);
CREATE INDEX idx_systems_property_id ON systems(property_id);
CREATE INDEX idx_simulations_property_id ON simulations(property_id);

-- Trigger for updated_at (optional but recommended)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
CREATE TRIGGER update_properties_updated_at BEFORE UPDATE ON properties FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
CREATE TRIGGER update_simulations_updated_at BEFORE UPDATE ON simulations FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
