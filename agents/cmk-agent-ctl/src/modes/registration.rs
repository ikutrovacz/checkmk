// Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
// This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
// conditions defined in the file COPYING, which is part of this source code package.

use crate::{agent_receiver_api, certs, config, constants, site_spec, types};
use anyhow::{anyhow, Context, Result as AnyhowResult};

trait TrustEstablishing {
    fn prompt_server_certificate(&self, coordinates: &site_spec::Coordinates) -> AnyhowResult<()>;
    fn prompt_password(&self, user: &str) -> AnyhowResult<String>;
}

struct InteractiveTrust {}

impl InteractiveTrust {
    fn display_cert(server: &str, port: &u16) -> AnyhowResult<()> {
        let pem_str = certs::fetch_server_cert_pem(server, port)?;
        let pem = certs::parse_pem(&pem_str)?;
        let x509 = pem.parse_x509()?;
        let validity = x509.validity();

        eprintln!("PEM-encoded certificate:\n{}", pem_str);
        eprintln!(
            "Issued by:\n\t{}",
            certs::common_names(x509.issuer())?.join(", ")
        );
        eprintln!(
            "Issued to:\n\t{}",
            certs::common_names(x509.subject())?.join(", ")
        );
        eprintln!(
            "Validity:\n\tFrom {}\n\tTo   {}",
            validity.not_before.to_rfc2822(),
            validity.not_after.to_rfc2822(),
        );
        Ok(())
    }
}

impl TrustEstablishing for InteractiveTrust {
    fn prompt_server_certificate(&self, coordinates: &site_spec::Coordinates) -> AnyhowResult<()> {
        eprintln!(
            "Attempting to register at {}. Server certificate details:\n",
            coordinates,
        );
        InteractiveTrust::display_cert(&coordinates.server, &coordinates.port)?;
        eprintln!();
        eprintln!("Do you want to establish this connection? [Y/n]");
        eprint!("> ");
        loop {
            let mut answer = String::new();
            std::io::stdin()
                .read_line(&mut answer)
                .context("Failed to read answer from standard input")?;
            match answer.to_lowercase().trim() {
                "y" | "" => return Ok(()),
                "n" => {
                    return Err(anyhow!(format!(
                        "Cannot continue without trusting {}",
                        coordinates
                    )))
                }
                _ => {
                    eprintln!("Please answer 'y' or 'n'");
                    eprint!("> ");
                }
            }
        }
    }

    fn prompt_password(&self, user: &str) -> AnyhowResult<String> {
        eprintln!();
        eprint!("Please enter password for '{}'\n> ", user);
        rpassword::read_password().context("Failed to obtain API password")
    }
}

fn registration_server_cert<'a>(
    config: &'a config::RegistrationConnectionConfig,
    trust_establisher: &impl TrustEstablishing,
) -> AnyhowResult<Option<&'a str>> {
    match &config.root_certificate {
        Some(cert) => {
            if config.trust_server_cert {
                eprintln!(
                    "Blind trust of server certificate enabled but a root certificate was \
                     given in the configuration and will be used to verify the server certificate."
                );
            }
            Ok(Some(cert.as_str()))
        }
        None => {
            if !config.trust_server_cert {
                trust_establisher.prompt_server_certificate(&config.coordinates)?;
            }
            Ok(None)
        }
    }
}

fn prepare_registration(
    config: &config::RegistrationConnectionConfig,
    agent_rec_api: &impl agent_receiver_api::Pairing,
    trust_establisher: &impl TrustEstablishing,
) -> AnyhowResult<(types::Credentials, PairingResult)> {
    let uuid = uuid::Uuid::new_v4();
    let (csr, private_key) = certs::make_csr(&uuid.to_string()).context("Error creating CSR.")?;
    let root_cert = registration_server_cert(config, trust_establisher)?;
    let credentials = types::Credentials {
        username: config.username.clone(),
        password: if let Some(password) = &config.password {
            String::from(password)
        } else {
            trust_establisher.prompt_password(&config.username)?
        },
    };
    let pairing_response = agent_rec_api
        .pair(&config.coordinates.to_url()?, root_cert, csr, &credentials)
        .context(format!("Error pairing with {}", &config.coordinates))?;
    Ok((
        credentials,
        PairingResult {
            uuid,
            private_key,
            pairing_response,
        },
    ))
}

struct PairingResult {
    uuid: uuid::Uuid,
    private_key: String,
    pairing_response: agent_receiver_api::PairingResponse,
}

trait RegistrationEndpointCall {
    fn call(
        &self,
        config: &config::RegistrationConnectionConfig,
        credentials: &types::Credentials,
        pairing_result: &PairingResult,
        agent_rec_api: &impl agent_receiver_api::Registration,
    ) -> AnyhowResult<()>;
}

struct HostNameRegistration<'a> {
    host_name: &'a str,
}

impl RegistrationEndpointCall for HostNameRegistration<'_> {
    fn call(
        &self,
        config: &config::RegistrationConnectionConfig,
        credentials: &types::Credentials,
        pairing_result: &PairingResult,
        agent_rec_api: &impl agent_receiver_api::Registration,
    ) -> AnyhowResult<()> {
        agent_rec_api
            .register_with_hostname(
                &config.coordinates.to_url()?,
                &pairing_result.pairing_response.root_cert,
                credentials,
                &pairing_result.uuid,
                self.host_name,
            )
            .context(format!(
                "Error registering with host name at {}",
                &config.coordinates
            ))
    }
}

struct AgentLabelsRegistration<'a> {
    agent_labels: &'a types::AgentLabels,
}

impl RegistrationEndpointCall for AgentLabelsRegistration<'_> {
    fn call(
        &self,
        config: &config::RegistrationConnectionConfig,
        credentials: &types::Credentials,
        pairing_result: &PairingResult,
        agent_rec_api: &impl agent_receiver_api::Registration,
    ) -> AnyhowResult<()> {
        agent_rec_api
            .register_with_agent_labels(
                &config.coordinates.to_url()?,
                &pairing_result.pairing_response.root_cert,
                credentials,
                &pairing_result.uuid,
                self.agent_labels,
            )
            .context(format!(
                "Error registering with agent labels at {}",
                &config.coordinates
            ))
    }
}

fn post_registration_conn_type(
    coordinates: &site_spec::Coordinates,
    connection: &config::TrustedConnection,
    agent_rec_api: &impl agent_receiver_api::Status,
) -> AnyhowResult<config::ConnectionType> {
    loop {
        let status_resp = agent_rec_api.status(&coordinates.to_url()?, connection)?;
        if let Some(agent_receiver_api::HostStatus::Declined) = status_resp.status {
            return Err(anyhow!(
                "Registration declined by Checkmk instance{}",
                if let Some(msg) = status_resp.message {
                    format!(": {}", msg)
                } else {
                    String::from("")
                }
            ));
        }
        if let Some(ct) = status_resp.connection_type {
            return Ok(ct);
        }
        println!("Waiting for registration to complete on Checkmk instance, sleeping 20 s");
        std::thread::sleep(std::time::Duration::from_secs(20));
    }
}

fn direct_registration(
    config: &config::RegistrationConnectionConfig,
    registry: &mut config::Registry,
    agent_rec_api: &(impl agent_receiver_api::Pairing
          + agent_receiver_api::Registration
          + agent_receiver_api::Status),
    trust_establisher: &impl TrustEstablishing,
    endpoint_call: &impl RegistrationEndpointCall,
) -> AnyhowResult<()> {
    let (credentials, pairing_result) =
        prepare_registration(config, agent_rec_api, trust_establisher)?;

    endpoint_call.call(config, &credentials, &pairing_result, agent_rec_api)?;

    let connection = config::TrustedConnectionWithRemote {
        trust: config::TrustedConnection {
            uuid: pairing_result.uuid,
            private_key: pairing_result.private_key,
            certificate: pairing_result.pairing_response.client_cert,
            root_cert: pairing_result.pairing_response.root_cert,
        },
    };
    registry.register_connection(
        post_registration_conn_type(&config.coordinates, &connection.trust, agent_rec_api)?,
        &config.coordinates,
        connection,
    );

    registry.save()?;

    Ok(())
}

fn proxy_registration(
    config: &config::RegistrationConfigHostName,
    agent_rec_api: &(impl agent_receiver_api::Pairing + agent_receiver_api::Registration),
    trust_establisher: &impl TrustEstablishing,
) -> AnyhowResult<()> {
    let (credentials, pairing_result) =
        prepare_registration(&config.connection_config, agent_rec_api, trust_establisher)?;

    HostNameRegistration {
        host_name: &config.host_name,
    }
    .call(
        &config.connection_config,
        &credentials,
        &pairing_result,
        agent_rec_api,
    )?;

    println!(
        "{}",
        serde_json::to_string(&ProxyPullData {
            agent_controller_version: String::from(constants::VERSION),
            connection: config::TrustedConnection {
                uuid: pairing_result.uuid,
                private_key: pairing_result.private_key,
                certificate: pairing_result.pairing_response.client_cert,
                root_cert: pairing_result.pairing_response.root_cert,
            }
        })?
    );
    Ok(())
}

#[derive(serde::Serialize, serde::Deserialize)]
pub struct ProxyPullData {
    pub agent_controller_version: String,
    pub connection: config::TrustedConnection,
}

pub fn register_host_name(
    config: &config::RegistrationConfigHostName,
    registry: &mut config::Registry,
) -> AnyhowResult<()> {
    direct_registration(
        &config.connection_config,
        registry,
        &agent_receiver_api::Api {
            use_proxy: config.connection_config.client_config.use_proxy,
        },
        &InteractiveTrust {},
        &HostNameRegistration {
            host_name: &config.host_name,
        },
    )?;
    println!("Registration complete.");
    Ok(())
}

pub fn register_agent_labels(
    config: &config::RegistrationConfigAgentLabels,
    registry: &mut config::Registry,
) -> AnyhowResult<()> {
    direct_registration(
        &config.connection_config,
        registry,
        &agent_receiver_api::Api {
            use_proxy: config.connection_config.client_config.use_proxy,
        },
        &InteractiveTrust {},
        &AgentLabelsRegistration {
            agent_labels: &config.agent_labels,
        },
    )?;
    println!("Registration complete. It may take few minutes until the newly created host and its services are visible in the site.");
    Ok(())
}

pub fn proxy_register(config: &config::RegistrationConfigHostName) -> AnyhowResult<()> {
    proxy_registration(
        config,
        &agent_receiver_api::Api {
            use_proxy: config.connection_config.client_config.use_proxy,
        },
        &InteractiveTrust {},
    )
}

#[cfg(test)]
mod tests {
    use std::str::FromStr;

    use super::*;

    const SITE_COORDINATES: &str = "server:8000/host";
    const SITE_URL: &str = "https://server:8000/host";
    const HOST_NAME: &str = "host";
    const USERNAME: &str = "user";

    enum RegistrationMethod {
        HostName,
        AgentLabels,
    }

    struct MockApi {
        expect_root_cert_for_pairing: bool,
        expected_registration_method: Option<RegistrationMethod>,
    }

    impl agent_receiver_api::Pairing for MockApi {
        fn pair(
            &self,
            base_url: &reqwest::Url,
            root_cert: Option<&str>,
            _csr: String,
            _credentials: &types::Credentials,
        ) -> AnyhowResult<agent_receiver_api::PairingResponse> {
            assert!(base_url.to_string() == SITE_URL);
            assert!(root_cert.is_some() == self.expect_root_cert_for_pairing);
            Ok(agent_receiver_api::PairingResponse {
                root_cert: String::from("root_cert"),
                client_cert: String::from("client_cert"),
            })
        }
    }

    impl agent_receiver_api::Registration for MockApi {
        fn register_with_hostname(
            &self,
            base_url: &reqwest::Url,
            _root_cert: &str,
            _credentials: &types::Credentials,
            _uuid: &uuid::Uuid,
            host_name: &str,
        ) -> AnyhowResult<()> {
            assert!(matches!(
                self.expected_registration_method.as_ref().unwrap(),
                RegistrationMethod::HostName
            ));
            assert!(base_url.to_string() == SITE_URL);
            assert!(host_name == HOST_NAME);
            Ok(())
        }

        fn register_with_agent_labels(
            &self,
            base_url: &reqwest::Url,
            _root_cert: &str,
            _credentials: &types::Credentials,
            _uuid: &uuid::Uuid,
            ag_labels: &types::AgentLabels,
        ) -> AnyhowResult<()> {
            assert!(matches!(
                self.expected_registration_method.as_ref().unwrap(),
                RegistrationMethod::AgentLabels
            ));
            assert!(base_url.to_string() == SITE_URL);
            assert!(ag_labels == &agent_labels());
            Ok(())
        }
    }

    impl agent_receiver_api::Status for MockApi {
        fn status(
            &self,
            base_url: &reqwest::Url,
            _connection: &config::TrustedConnection,
        ) -> AnyhowResult<agent_receiver_api::StatusResponse> {
            assert!(base_url.to_string() == SITE_URL);
            Ok(agent_receiver_api::StatusResponse {
                hostname: Some(String::from(HOST_NAME)),
                status: None,
                connection_type: Some(config::ConnectionType::Pull),
                message: None,
            })
        }
    }

    struct MockInteractiveTrust {
        expect_server_cert_prompt: bool,
        expect_password_prompt: bool,
    }

    impl TrustEstablishing for MockInteractiveTrust {
        fn prompt_server_certificate(
            &self,
            coordinates: &site_spec::Coordinates,
        ) -> AnyhowResult<()> {
            assert!(self.expect_server_cert_prompt);
            assert_eq!(coordinates.to_string(), SITE_COORDINATES);
            Ok(())
        }

        fn prompt_password(&self, user: &str) -> AnyhowResult<String> {
            assert!(self.expect_password_prompt);
            assert_eq!(user, USERNAME);
            Ok(String::from("password"))
        }
    }

    fn registry() -> config::Registry {
        config::Registry::new(
            config::RegisteredConnections::default(),
            tempfile::NamedTempFile::new().unwrap(),
        )
        .unwrap()
    }

    fn agent_labels() -> types::AgentLabels {
        let mut al = std::collections::HashMap::new();
        al.insert(String::from("a"), String::from("b"));
        al
    }

    fn registration_connection_config(
        root_certificate: Option<String>,
        password: Option<String>,
        trust_server_cert: bool,
    ) -> config::RegistrationConnectionConfig {
        config::RegistrationConnectionConfig {
            coordinates: site_spec::Coordinates::from_str(SITE_COORDINATES).unwrap(),
            username: String::from(USERNAME),
            password,
            root_certificate,
            trust_server_cert,
            client_config: config::ClientConfig {
                use_proxy: false,
                validate_api_cert: false,
            },
        }
    }

    mod test_pair {
        use super::*;

        #[test]
        fn test_interactive_trust() {
            assert!(prepare_registration(
                &registration_connection_config(None, None, false),
                &MockApi {
                    expect_root_cert_for_pairing: false,
                    expected_registration_method: None,
                },
                &MockInteractiveTrust {
                    expect_server_cert_prompt: true,
                    expect_password_prompt: true,
                },
            )
            .is_ok());
        }

        #[test]
        fn test_blind_trust() {
            assert!(prepare_registration(
                &registration_connection_config(None, Some(String::from("password")), true),
                &MockApi {
                    expect_root_cert_for_pairing: false,
                    expected_registration_method: None,
                },
                &MockInteractiveTrust {
                    expect_server_cert_prompt: false,
                    expect_password_prompt: false,
                },
            )
            .is_ok());
        }

        #[test]
        fn test_root_cert_from_config() {
            assert!(prepare_registration(
                &registration_connection_config(
                    Some(String::from("root_certificate")),
                    Some(String::from("password")),
                    false
                ),
                &MockApi {
                    expect_root_cert_for_pairing: true,
                    expected_registration_method: None,
                },
                &MockInteractiveTrust {
                    expect_server_cert_prompt: false,
                    expect_password_prompt: false,
                },
            )
            .is_ok());
        }

        #[test]
        fn test_root_cert_from_config_and_blind_trust() {
            assert!(prepare_registration(
                &registration_connection_config(Some(String::from("root_certificate")), None, true),
                &MockApi {
                    expect_root_cert_for_pairing: true,
                    expected_registration_method: None,
                },
                &MockInteractiveTrust {
                    expect_server_cert_prompt: false,
                    expect_password_prompt: true,
                },
            )
            .is_ok());
        }
    }

    mod test_register {
        use super::*;

        #[test]
        fn test_host_name() {
            let mut registry = registry();
            assert!(!registry.path().exists());
            assert!(direct_registration(
                &registration_connection_config(None, None, false),
                &mut registry,
                &MockApi {
                    expect_root_cert_for_pairing: false,
                    expected_registration_method: Some(RegistrationMethod::HostName),
                },
                &MockInteractiveTrust {
                    expect_server_cert_prompt: true,
                    expect_password_prompt: true,
                },
                &HostNameRegistration {
                    host_name: HOST_NAME
                },
            )
            .is_ok());
            assert!(!registry.is_empty());
            assert!(registry.path().exists());
        }

        #[test]
        fn test_agent_labels() {
            let mut registry = registry();
            assert!(!registry.path().exists());
            assert!(direct_registration(
                &registration_connection_config(
                    Some(String::from("root_certificate")),
                    Some(String::from("password")),
                    false
                ),
                &mut registry,
                &MockApi {
                    expect_root_cert_for_pairing: true,
                    expected_registration_method: Some(RegistrationMethod::AgentLabels),
                },
                &MockInteractiveTrust {
                    expect_server_cert_prompt: false,
                    expect_password_prompt: false,
                },
                &AgentLabelsRegistration {
                    agent_labels: &agent_labels()
                },
            )
            .is_ok());
            assert!(!registry.is_empty());
            assert!(registry.path().exists());
        }
    }

    #[test]
    fn test_proxy() {
        assert!(proxy_registration(
            &config::RegistrationConfigHostName {
                connection_config: registration_connection_config(None, None, true),
                host_name: String::from(HOST_NAME),
            },
            &MockApi {
                expect_root_cert_for_pairing: false,
                expected_registration_method: Some(RegistrationMethod::HostName),
            },
            &MockInteractiveTrust {
                expect_server_cert_prompt: false,
                expect_password_prompt: true,
            },
        )
        .is_ok());
    }
}
