import { TestBed } from '@angular/core/testing';

import { Speechservice } from './speechservice';

describe('Speechservice', () => {
  let service: Speechservice;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(Speechservice);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
