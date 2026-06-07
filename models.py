from dataclasses import dataclass


@dataclass
class Company:
    domain: str
    name: str


@dataclass
class Contact:
    person_id: str
    first_name: str
    last_name: str
    email: str | None
    linkedin_url: str
    job_title: str
    company_domain: str
    company_name: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
