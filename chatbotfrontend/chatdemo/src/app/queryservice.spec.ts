import { TestBed } from '@angular/core/testing';

import { Queryservice } from './queryservice';

describe('Queryservice', () => {
  let service: Queryservice;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(Queryservice);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
