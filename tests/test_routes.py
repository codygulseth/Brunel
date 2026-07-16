def test_main_html_routes(client):
    for path in ["/","/organizations","/people","/responsibilities","/projects/1"]:
        response=client.get(path);assert response.status_code==200;assert "Brunel" in response.text

def test_api_success_responses(client):
    assert len(client.get("/api/projects").json())==1
    assert client.get("/api/projects/1").json()["name"]=="Project Northstar Data Center"
    assert len(client.get("/api/projects/1/organizations").json())==16
    assert len(client.get("/api/projects/1/people").json())==25
    rs=client.get("/api/projects/1/responsibilities").json();assert len(rs)==35
    assert client.get(f"/api/responsibilities/{rs[0]['id']}").status_code==200

def test_api_filters_and_search(client):
    assert len(client.get("/api/projects/1/organizations",params={"organization_type":"Supplier"}).json())==2
    assert len(client.get("/api/projects/1/people",params={"project_role":"Engineer of Record"}).json())==4
    assert len(client.get("/api/projects/1/responsibilities",params={"category":"Procurement"}).json())==3
    assert len(client.get("/api/projects/1/responsibilities",params={"search":"functional performance"}).json())==1

def test_api_validation_errors(client):
    assert client.get("/api/projects/999").status_code==404
    assert client.get("/api/projects/1/organizations",params={"organization_type":"Invalid"}).status_code==422
    response=client.post("/api/projects/1/organizations",json={"name":"","organization_type":"Owner","primary_discipline":"Owner","contractual_relationship":"Direct"})
    assert response.status_code==422

def test_post_endpoints(client):
    org=client.post("/api/projects/1/organizations",json={"name":"Fictional Test Consultant","organization_type":"Consultant","primary_discipline":"Other","contractual_relationship":"Test only"})
    assert org.status_code==201;oid=org.json()["id"]
    person=client.post("/api/projects/1/people",json={"organization_id":oid,"full_name":"Test Person","job_title":"Analyst","email":"test@example.test","phone":"555-0100","project_role":"Project Manager","discipline":"Other"})
    assert person.status_code==201
    resp=client.post("/api/projects/1/responsibilities",json={"organization_id":oid,"person_id":person.json()["id"],"category":"Coordination","description":"Test coordination","decision_authority":"Recorded test decisions","approval_authority":"None","source_type":"Manual Entry","source_reference":"Test fixture"})
    assert resp.status_code==201
